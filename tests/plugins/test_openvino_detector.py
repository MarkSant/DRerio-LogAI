"""Tests for ``zebtrack.plugins.openvino_detector``.

The plugin's own code runs for real — device and config selection, compile
fallback, output discovery, letterboxing, the Ultralytics NMS, box rescaling,
mask decoding, the async batch queue — against the in-memory OpenVINO runtime
of ``tests/helpers/fake_backends.py``. Only the runtime itself is faked, so
every expected value below is derived from the geometry of the input, not from
what the code happens to return.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pytest

pytest.importorskip("torch")

from tests.helpers.fake_backends import (
    FakeOpenVINO,
    detection_tensor,
    install_fake_openvino,
    openvino_settings,
    write_openvino_model_dir,
)

from zebtrack.plugins import openvino_detector as module
from zebtrack.plugins.openvino_detector import (
    OpenVINOPlugin,
    _letterbox,
    _OutputProxy,
    _resolve_openvino_cache_dir,
    _scale_image,
)
from zebtrack.settings import DEFAULT_MATCH_THRESHOLD, DEFAULT_TRACK_THRESHOLD
from zebtrack.utils import IntegrityError, calculate_sha256

pytestmark = pytest.mark.unit

ZEBRAFISH = {0: "aqua", 1: "zebrafish"}
BARNES = {0: "arena", 1: "experimenter", 2: "rat"}

# A 640x480 frame letterboxed into 640x640 keeps its scale and gains 80 px of
# padding above and below. A box centred at (320, 320) in model input is
# therefore centred at (320, 240) in the frame.
FRAME_HW = (480, 640)
PAD_Y = 80


def _frame(hw: tuple[int, int] = FRAME_HW) -> np.ndarray:
    return np.zeros((*hw, 3), dtype=np.uint8)


@pytest.fixture
def model_dir(tmp_path: Path) -> Path:
    return write_openvino_model_dir(tmp_path / "model", class_names=ZEBRAFISH)


def _build(
    monkeypatch: pytest.MonkeyPatch,
    directory: Path,
    *,
    backend: FakeOpenVINO | None = None,
    settings_obj: Any | None = None,
    mode: str = "live",
    expected_hash: str | None = None,
) -> tuple[OpenVINOPlugin, FakeOpenVINO]:
    backend = install_fake_openvino(monkeypatch, backend)
    plugin = OpenVINOPlugin(
        directory,
        expected_hash=expected_hash,
        settings_obj=settings_obj,
        mode=mode,  # type: ignore[arg-type]
    )
    return plugin, backend


def _seg_backend() -> FakeOpenVINO:
    """A two-class segmentation model: 32 mask coefficients and a 160x160 proto."""
    return FakeOpenVINO(output_dims=((1, 4 + 2 + 32, 16), (1, 32, 160, 160)))


def _seg_tensors(box: tuple[float, float, float, float, float, int]) -> tuple[Any, Any]:
    """Detection + proto tensors whose mask is exactly the box, filled.

    Mask logits are ``coefficients @ protos``. One coefficient of 1 against a
    proto channel that is +10 everywhere gives a mask that is "on" over the
    whole image; ``process_mask`` then crops it to the box.
    """
    det = detection_tensor([box], num_classes=2, num_masks=32)
    det[0, 4 + 2, 0] = 1.0
    proto = np.zeros((1, 32, 160, 160), dtype=np.float32)
    proto[0, 0] = 10.0
    return det, proto


# ---------------------------------------------------------------------------
# Cache directory resolution
# ---------------------------------------------------------------------------


class TestCacheDir:
    @pytest.mark.parametrize("raw", [None, ""])
    def test_no_directory_means_no_cache(self, raw: str | None) -> None:
        assert _resolve_openvino_cache_dir(raw) is None

    def test_an_absolute_directory_is_created_and_returned(self, tmp_path: Path) -> None:
        target = tmp_path / "nested" / "ov_cache"
        assert _resolve_openvino_cache_dir(target) == str(target)
        assert target.is_dir()

    def test_a_relative_directory_is_anchored_to_the_repository_root(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The root is three parents above the module file, never the CWD: the
        # cache must survive a ``cd`` and be shared by processes started elsewhere.
        fake_module = tmp_path / "root" / "src" / "zebtrack" / "plugins" / "openvino_detector.py"
        monkeypatch.setattr(module, "__file__", str(fake_module))
        monkeypatch.chdir(tmp_path)

        resolved = _resolve_openvino_cache_dir("openvino_model_cache")

        assert resolved == str((tmp_path / "root").resolve() / "openvino_model_cache")
        assert Path(resolved).is_dir()
        assert not (tmp_path / "openvino_model_cache").exists()

    def test_a_directory_that_cannot_be_created_falls_back_to_the_tempdir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        blocker = tmp_path / "a_file"
        blocker.write_text("not a directory", encoding="utf-8")
        temp_root = tmp_path / "temp"
        temp_root.mkdir()
        monkeypatch.setattr("tempfile.gettempdir", lambda: str(temp_root))

        resolved = _resolve_openvino_cache_dir(blocker / "ov_cache")

        assert resolved == str(temp_root / "zebtrack_openvino_cache")
        assert Path(resolved).is_dir()

    def test_an_unwritable_directory_falls_back_to_the_tempdir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = tmp_path / "read_only"
        temp_root = tmp_path / "temp"
        temp_root.mkdir()
        monkeypatch.setattr("tempfile.gettempdir", lambda: str(temp_root))
        monkeypatch.setattr(module.os, "access", lambda path, mode: False)

        resolved = _resolve_openvino_cache_dir(target)

        assert resolved == str(temp_root / "zebtrack_openvino_cache")
        assert Path(resolved).is_dir()


# ---------------------------------------------------------------------------
# Letterboxing and mask resizing
# ---------------------------------------------------------------------------


class TestLetterbox:
    def test_a_landscape_frame_is_padded_top_and_bottom(self) -> None:
        img = np.full((480, 640, 3), 200, dtype=np.uint8)
        out, ratio, (dw, dh) = _letterbox(img, new_shape=(640, 640), auto=False)

        assert out.shape == (640, 640, 3)
        assert ratio == (1.0, 1.0)
        assert (dw, dh) == (0.0, 80.0)
        # Padding is the Ultralytics grey; the image sits untouched between the bands.
        assert (out[:80] == 114).all()
        assert (out[560:] == 114).all()
        assert (out[80:560] == 200).all()

    def test_a_small_frame_is_scaled_up_to_fill_the_longer_side(self) -> None:
        out, ratio, (dw, dh) = _letterbox(_frame((240, 320)), new_shape=(640, 640), auto=False)
        assert out.shape == (640, 640, 3)
        assert ratio == (2.0, 2.0)
        assert (dw, dh) == (0.0, 80.0)

    def test_scaleup_false_never_enlarges(self) -> None:
        img = np.full((100, 200, 3), 9, dtype=np.uint8)
        out, ratio, (dw, dh) = _letterbox(img, new_shape=(640, 640), auto=False, scaleup=False)
        assert out.shape == (640, 640, 3)
        assert ratio == (1.0, 1.0)
        assert (dw, dh) == (220.0, 270.0)
        assert (out[270:370, 220:420] == 9).all()

    def test_auto_pads_only_up_to_the_next_stride_multiple(self) -> None:
        # 640 - 500 = 140 px to spare; modulo the 32 px stride that is 12, split in two.
        out, _ratio, (dw, dh) = _letterbox(_frame((500, 640)), new_shape=(640, 640), auto=True)
        assert (dw, dh) == (0.0, 6.0)
        assert out.shape == (512, 640, 3)

    def test_scale_fill_stretches_without_padding(self) -> None:
        out, ratio, (dw, dh) = _letterbox(
            _frame((500, 640)), new_shape=(640, 640), auto=False, scaleFill=True
        )
        assert out.shape == (640, 640, 3)
        assert ratio == (1.0, 1.28)
        assert (dw, dh) == (0.0, 0.0)

    def test_an_integer_shape_means_a_square(self) -> None:
        out, _ratio, _pad = _letterbox(_frame(), new_shape=320, auto=False)  # type: ignore[arg-type]
        assert out.shape == (320, 320, 3)

    @pytest.mark.parametrize(
        "img",
        [None, np.zeros((0, 0, 3), dtype=np.uint8), np.zeros((0, 640, 3), dtype=np.uint8)],
    )
    def test_an_empty_image_is_rejected(self, img: Any) -> None:
        with pytest.raises(ValueError, match="None or empty"):
            _letterbox(img)

    def test_a_one_dimensional_array_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="at least 2 dimensions"):
            _letterbox(np.zeros(12, dtype=np.uint8))


class TestScaleImage:
    def test_masks_of_the_same_aspect_are_simply_resized(self) -> None:
        masks = np.zeros((20, 40, 2), dtype=np.float32)
        masks[:, :20, 0] = 1.0  # left half of channel 0
        out = _scale_image(masks, (40, 80))

        assert out.shape == (40, 80, 2)
        assert out[20, 10, 0] == pytest.approx(1.0)
        assert out[20, 70, 0] == pytest.approx(0.0)
        assert not out[..., 1].any()

    def test_the_letterbox_bands_are_cropped_before_resizing(self) -> None:
        # A 640x480 frame occupies rows 80..560 of a 640x640 model input. A mask
        # covering input rows 260..380 therefore covers frame rows 180..300 —
        # not 195..285, which is what resizing the padded mask would give.
        masks = np.zeros((640, 640, 1), dtype=np.float32)
        masks[260:380, 220:420, 0] = 1.0
        out = _scale_image(masks, (480, 640))

        assert out.shape == (480, 640)
        rows = np.flatnonzero(out[:, 320] > 0.5)
        cols = np.flatnonzero(out[240, :] > 0.5)
        assert (int(rows[0]), int(rows[-1])) == (180, 299)
        assert (int(cols[0]), int(cols[-1])) == (220, 419)

    def test_a_portrait_frame_loses_its_side_bands(self) -> None:
        masks = np.zeros((640, 640, 1), dtype=np.float32)
        masks[100:200, 80:560, 0] = 1.0  # the full width of the un-padded area
        out = _scale_image(masks, (640, 480))

        cols = np.flatnonzero(out[150, :] > 0.5)
        assert out.shape == (640, 480)
        assert (int(cols[0]), int(cols[-1])) == (0, 479)


class TestOutputProxy:
    def test_tensors_are_served_by_their_output_key(self) -> None:
        det, proto = np.ones(3), np.zeros(2)
        proxy = _OutputProxy(det_tensor=det, proto_tensor=proto, det_key="d", proto_key="p")
        assert proxy["d"] is det
        assert proxy["p"] is proto
        assert "p" in proxy

    def test_a_detection_only_model_has_no_proto_entry(self) -> None:
        proxy = _OutputProxy(det_tensor=np.ones(3), proto_tensor=None, det_key="d", proto_key=None)
        assert "d" in proxy
        assert None not in proxy


# ---------------------------------------------------------------------------
# Construction: integrity, device, configuration, outputs, class names
# ---------------------------------------------------------------------------


class TestIntegrity:
    def test_a_directory_without_xml_is_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="Could not find a .xml model file"):
            OpenVINOPlugin(tmp_path)

    def test_a_string_path_is_accepted(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            OpenVINOPlugin(str(tmp_path))

    def test_a_hash_mismatch_refuses_to_load(
        self, model_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        backend = install_fake_openvino(monkeypatch)
        with pytest.raises(IntegrityError, match=r"'model\.xml' could not be verified"):
            OpenVINOPlugin(model_dir, expected_hash="0" * 64)
        # The integrity check comes BEFORE the model is handed to the runtime.
        assert backend.models == []

    def test_the_matching_hash_loads(
        self, model_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        digest = calculate_sha256(str(model_dir / "model.xml"))
        _plugin, backend = _build(monkeypatch, model_dir, expected_hash=digest)
        assert [model.path for model in backend.models] == [str(model_dir / "model.xml")]

    def test_a_missing_openvino_runtime_is_an_import_error(
        self, model_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(module, "OPENVINO_AVAILABLE", False)
        with pytest.raises(ImportError, match="OpenVINO is not available"):
            OpenVINOPlugin(model_dir)

    def test_a_missing_torch_is_an_import_error(
        self, model_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        install_fake_openvino(monkeypatch)
        monkeypatch.setattr(module, "TORCH_AVAILABLE", False)
        with pytest.raises(ImportError, match="PyTorch is required"):
            OpenVINOPlugin(model_dir)

    def test_the_plugin_names_itself(self) -> None:
        assert OpenVINOPlugin.get_name() == "OpenVINO"


class TestThresholds:
    def test_without_settings_the_documented_defaults_apply(
        self, model_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        plugin, backend = _build(monkeypatch, model_dir)
        assert (plugin.conf_threshold, plugin.nms_threshold) == (0.25, 0.45)
        assert (plugin.track_threshold, plugin.match_threshold) == (
            DEFAULT_TRACK_THRESHOLD,
            DEFAULT_MATCH_THRESHOLD,
        )
        assert backend.compile_calls == [("AUTO", {"PERFORMANCE_HINT": "LATENCY"})]

    def test_settings_supply_the_thresholds(
        self, model_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        plugin, _backend = _build(monkeypatch, model_dir, settings_obj=openvino_settings())
        assert (plugin.conf_threshold, plugin.nms_threshold) == (0.4, 0.5)
        assert (plugin.track_threshold, plugin.match_threshold) == (0.6, 0.85)

    def test_the_animal_threshold_wins_over_the_arena_one(
        self, model_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings_obj = openvino_settings()
        settings_obj.yolo_model.animal_confidence_threshold = 0.7
        plugin, _backend = _build(monkeypatch, model_dir, settings_obj=settings_obj)
        assert plugin.conf_threshold == 0.7

    def test_context_and_region_setters(
        self, model_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        plugin, _backend = _build(monkeypatch, model_dir)
        assert (plugin._context, plugin._aquarium_region_defined) == ("tracking", False)
        plugin.set_context("analysis")
        plugin.set_aquarium_region_defined(1)  # type: ignore[arg-type]
        assert plugin._context == "analysis"
        assert plugin._aquarium_region_defined is True


class TestDeviceAndConfig:
    def _compile(
        self,
        monkeypatch: pytest.MonkeyPatch,
        directory: Path,
        *,
        backend: FakeOpenVINO | None = None,
        mode: str = "live",
        **openvino_overrides: Any,
    ) -> list[tuple[str, dict[str, Any]]]:
        _plugin, backend = _build(
            monkeypatch,
            directory,
            backend=backend,
            settings_obj=openvino_settings(**openvino_overrides),
            mode=mode,
        )
        return backend.compile_calls

    def test_live_mode_uses_the_live_device_and_hint(
        self, model_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = self._compile(monkeypatch, model_dir, device="CPU", device_batch="GPU")
        assert calls == [("CPU", {"PERFORMANCE_HINT": "LATENCY"})]

    def test_batch_mode_uses_the_batch_device_and_hint(
        self, model_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = self._compile(
            monkeypatch, model_dir, mode="batch", device="CPU", device_batch="GPU"
        )
        assert calls == [("GPU", {"PERFORMANCE_HINT": "THROUGHPUT"})]

    def test_a_device_the_machine_lacks_becomes_auto(
        self, model_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # NPU requested on a CPU+GPU machine: AUTO, and none of the NPU-only keys.
        calls = self._compile(monkeypatch, model_dir, device="NPU", npu_turbo=True)
        assert calls == [("AUTO", {"PERFORMANCE_HINT": "LATENCY"})]

    @pytest.mark.parametrize(
        ("device", "precision", "expected"),
        [
            ("GPU", "FP16", "f16"),
            ("GPU", "INT8", "i8"),
            ("GPU", "FP32", None),
            # The precision hint is a GPU/NPU knob: on CPU it is not sent at all.
            ("CPU", "FP16", None),
        ],
    )
    def test_the_precision_hint_is_only_sent_to_gpu_class_devices(
        self,
        model_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
        device: str,
        precision: str,
        expected: str | None,
    ) -> None:
        calls = self._compile(monkeypatch, model_dir, device=device, precision=precision)
        assert calls[0][0] == device
        assert calls[0][1].get("INFERENCE_PRECISION_HINT") == expected

    def test_npu_defaults_to_fp16_and_honours_turbo(
        self, model_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        backend = FakeOpenVINO(available_devices=("CPU", "NPU"))
        calls = self._compile(monkeypatch, model_dir, backend=backend, device="NPU", npu_turbo=True)
        assert calls == [
            (
                "NPU",
                {
                    "PERFORMANCE_HINT": "LATENCY",
                    "INFERENCE_PRECISION_HINT": "f16",
                    "NPU_TURBO": True,
                },
            )
        ]

    def test_npu_without_turbo_sends_no_turbo_key(
        self, model_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        backend = FakeOpenVINO(available_devices=("CPU", "NPU"))
        calls = self._compile(
            monkeypatch, model_dir, backend=backend, device="NPU", precision="INT8"
        )
        assert calls == [("NPU", {"PERFORMANCE_HINT": "LATENCY", "INFERENCE_PRECISION_HINT": "i8"})]

    def test_stream_and_thread_counts_are_sent_as_strings(
        self, model_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = self._compile(monkeypatch, model_dir, device="CPU", num_streams=2, num_threads=6)
        assert calls == [
            (
                "CPU",
                {"PERFORMANCE_HINT": "LATENCY", "NUM_STREAMS": "2", "INFERENCE_NUM_THREADS": "6"},
            )
        ]

    def test_the_model_cache_is_opt_in(
        self, model_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cache = tmp_path / "cache"
        off = self._compile(monkeypatch, model_dir, cache_dir=str(cache))
        assert "CACHE_DIR" not in off[0][1]
        assert not cache.exists()

        on = self._compile(monkeypatch, model_dir, cache_dir=str(cache), enable_model_cache=True)
        assert on[0][1]["CACHE_DIR"] == str(cache)
        assert cache.is_dir()

    def test_a_failed_npu_compilation_retries_on_cpu_without_turbo(
        self, model_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        backend = FakeOpenVINO(available_devices=("CPU", "NPU"), failing_devices=("NPU",))
        calls = self._compile(monkeypatch, model_dir, backend=backend, device="NPU", npu_turbo=True)
        assert [device for device, _config in calls] == ["NPU", "CPU"]
        assert calls[1][1] == {"PERFORMANCE_HINT": "LATENCY", "INFERENCE_PRECISION_HINT": "f16"}
        assert backend.compiled[-1].device_name == "CPU"

    def test_a_failed_gpu_compilation_retries_on_auto_with_the_same_config(
        self, model_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        backend = FakeOpenVINO(failing_devices=("GPU",))
        calls = self._compile(
            monkeypatch, model_dir, backend=backend, device="GPU", precision="FP16"
        )
        assert [device for device, _config in calls] == ["GPU", "AUTO"]
        assert calls[1][1] == calls[0][1]

    def test_a_runtime_that_cannot_report_its_devices_still_loads(
        self, model_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # ``properties=None`` makes get_property("EXECUTION_DEVICES") raise.
        plugin, backend = _build(monkeypatch, model_dir, backend=FakeOpenVINO(properties=None))
        assert plugin.compiled_model is backend.compiled[-1]

    def test_execution_devices_are_queried_when_available(
        self, model_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        backend = FakeOpenVINO(properties={"EXECUTION_DEVICES": ["CPU"]})
        plugin, _backend = _build(monkeypatch, model_dir, backend=backend)
        assert plugin.compiled_model.get_property("EXECUTION_DEVICES") == ["CPU"]


class TestInputShape:
    def test_the_target_size_is_read_from_a_static_input(
        self, model_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        plugin, _backend = _build(
            monkeypatch, model_dir, backend=FakeOpenVINO(input_dims=(1, 3, 320, 320))
        )
        assert (plugin._target_h, plugin._target_w) == (320, 320)
        assert plugin.model_input_shape == (320, 320)

    def test_a_rectangular_model_gets_a_tensor_of_its_own_shape(
        self, model_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Height and width must not be swapped on the way to the letterbox.
        plugin, backend = _build(
            monkeypatch, model_dir, backend=FakeOpenVINO(input_dims=(1, 3, 384, 640))
        )
        assert (plugin._target_h, plugin._target_w) == (384, 640)
        assert plugin._preprocess(_frame()).shape == (1, 3, 384, 640)

        # 640x480 into 384x640: gain 0.8, 64 px of padding left and right.
        backend.compiled[-1].queue_results(
            detection_tensor([(320, 192, 80, 80, 0.9, 1)], num_classes=2)
        )
        assert plugin.detect(_frame()) == [(270, 190, 370, 290, pytest.approx(0.9), None, 1)]

    def test_a_dynamic_rank_input_keeps_the_640_default(
        self, model_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        plugin, _backend = _build(monkeypatch, model_dir, backend=FakeOpenVINO(input_dims=None))
        assert (plugin._target_h, plugin._target_w) == (640, 640)

    def test_an_unreadable_input_keeps_the_640_default(
        self, model_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        backend = FakeOpenVINO(input_dims=(1, 3, 320, 320))
        backend.model_input_error = RuntimeError("no input")
        plugin, _backend = _build(monkeypatch, model_dir, backend=backend)
        assert (plugin._target_h, plugin._target_w) == (640, 640)

    def test_warm_up_runs_one_blank_inference_at_the_model_size(
        self, model_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        plugin, _backend = _build(
            monkeypatch, model_dir, backend=FakeOpenVINO(input_dims=(1, 3, 320, 320))
        )
        (warm_up,) = plugin.infer_request.inputs
        assert warm_up.shape == (1, 3, 320, 320)
        assert warm_up.dtype == np.float32
        assert not warm_up.any()

    def test_a_failing_warm_up_does_not_prevent_loading(
        self, model_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        backend = FakeOpenVINO()
        backend.infer_error = RuntimeError("device busy")
        plugin, _backend = _build(monkeypatch, model_dir, backend=backend)
        assert plugin.infer_request.inputs == []
        assert plugin.class_names == ZEBRAFISH


class TestOutputsAndClassNames:
    @pytest.mark.parametrize("proto_first", [False, True])
    def test_outputs_are_told_apart_by_rank_not_by_position(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, proto_first: bool
    ) -> None:
        det, proto = (1, 38, 16), (1, 32, 160, 160)
        dims = (proto, det) if proto_first else (det, proto)
        directory = write_openvino_model_dir(tmp_path / "seg", class_names=ZEBRAFISH)
        plugin, backend = _build(monkeypatch, directory, backend=FakeOpenVINO(output_dims=dims))

        outputs = backend.compiled[-1].outputs
        assert plugin.output_det is outputs[1 if proto_first else 0]
        assert plugin.output_proto is outputs[0 if proto_first else 1]

    def test_without_a_rank_three_output_the_first_one_is_the_detection(
        self, model_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        plugin, backend = _build(
            monkeypatch, model_dir, backend=FakeOpenVINO(output_dims=((6, 16),))
        )
        assert plugin.output_det is backend.compiled[-1].outputs[0]
        assert plugin.output_proto is None

    def test_class_names_come_from_metadata_with_integer_keys(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        directory = write_openvino_model_dir(tmp_path / "barnes", class_names=BARNES)
        plugin, _backend = _build(
            monkeypatch, directory, backend=FakeOpenVINO(output_dims=((1, 7, 16),))
        )
        assert plugin.class_names == BARNES

    @pytest.mark.parametrize(
        ("output_dims", "expected"),
        [
            # Detection head: channels = 4 box + nc.
            (((1, 7, 16),), 3),
            # Segmentation head: channels = 4 box + nc + 32 mask coefficients.
            (((1, 38, 16), (1, 32, 160, 160)), 2),
            # Nothing to infer from: the historical two-class assumption.
            (((1, None, 16),), 2),
            # Never fewer than one class.
            (((1, 4, 16),), 1),
        ],
    )
    def test_without_metadata_the_class_count_is_inferred_from_the_head(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        output_dims: tuple[tuple[int | None, ...], ...],
        expected: int,
    ) -> None:
        directory = write_openvino_model_dir(tmp_path / "bare")
        plugin, _backend = _build(
            monkeypatch, directory, backend=FakeOpenVINO(output_dims=output_dims)
        )
        assert plugin.class_names == {i: f"class_{i}" for i in range(expected)}

    @pytest.mark.parametrize("metadata_text", ["{not json", '{"imgsz": 640}'])
    def test_unusable_metadata_falls_back_to_generic_names(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, metadata_text: str
    ) -> None:
        directory = write_openvino_model_dir(tmp_path / "bad", metadata_text=metadata_text)
        plugin, _backend = _build(monkeypatch, directory)
        assert plugin.class_names == {0: "class_0", 1: "class_1"}


# ---------------------------------------------------------------------------
# Inference: pre-processing, NMS, rescaling, masks
# ---------------------------------------------------------------------------


@pytest.fixture
def plugin(model_dir: Path, monkeypatch: pytest.MonkeyPatch) -> OpenVINOPlugin:
    built, _backend = _build(monkeypatch, model_dir)
    return built


class TestPreprocess:
    def test_the_tensor_is_normalised_rgb_in_nchw(self, plugin: OpenVINOPlugin) -> None:
        frame = _frame()
        frame[..., 0] = 255  # pure blue, in BGR
        tensor = plugin._preprocess(frame)

        assert tensor.shape == (1, 3, 640, 640)
        assert tensor.dtype == np.float32
        # Inside the image: R and G are 0, B (now the LAST channel) is 1.
        assert tensor[0, :, 320, 320].tolist() == [0.0, 0.0, 1.0]
        # In the letterbox band: grey 114 on every channel.
        assert tensor[0, :, 10, 320].tolist() == pytest.approx([114 / 255] * 3)

    def test_embedded_preprocessing_sends_the_raw_letterboxed_frame(
        self, plugin: OpenVINOPlugin
    ) -> None:
        plugin._use_embedded_preprocessing = True
        frame = _frame()
        frame[..., 0] = 255
        tensor = plugin._preprocess(frame)

        assert tensor.shape == (1, 640, 640, 3)
        assert tensor.dtype == np.uint8
        assert tensor[0, 320, 320].tolist() == [255, 0, 0]

    def test_without_cached_targets_the_input_layer_shape_is_used(
        self, plugin: OpenVINOPlugin
    ) -> None:
        del plugin._target_h, plugin._target_w
        plugin.input_layer = SimpleNamespace(shape=[1, 3, 320, 320])
        assert plugin._preprocess(_frame()).shape == (1, 3, 320, 320)

    def test_an_input_layer_of_unknown_rank_falls_back_to_640(self, plugin: OpenVINOPlugin) -> None:
        del plugin._target_h, plugin._target_w
        plugin.input_layer = SimpleNamespace(shape=[])
        assert plugin._preprocess(_frame()).shape == (1, 3, 640, 640)


class TestDetect:
    def test_a_box_is_mapped_back_through_the_letterbox(self, plugin: OpenVINOPlugin) -> None:
        plugin.compiled_model.queue_results(
            detection_tensor([(320, 320, 100, 80, 0.9, 1)], num_classes=2)
        )
        # Input box x 270..370, y 280..360; the frame starts 80 px lower.
        assert plugin.detect(_frame()) == [
            (270, 280 - PAD_Y, 370, 360 - PAD_Y, pytest.approx(0.9), None, 1)
        ]

    def test_a_smaller_frame_divides_by_the_letterbox_gain(self, plugin: OpenVINOPlugin) -> None:
        plugin.compiled_model.queue_results(
            detection_tensor([(320, 320, 100, 80, 0.9, 0)], num_classes=2)
        )
        # 320x240 is scaled 2x into the same 640x480 area.
        assert plugin.detect(_frame((240, 320))) == [
            (135, 100, 185, 140, pytest.approx(0.9), None, 0)
        ]

    def test_boxes_are_clipped_to_the_frame(self, plugin: OpenVINOPlugin) -> None:
        plugin.compiled_model.queue_results(
            detection_tensor([(20, 100, 100, 100, 0.9, 1)], num_classes=2)
        )
        # x -30..70 and y 50..150 in input; y -30..70 in the frame.
        assert plugin.detect(_frame()) == [(0, 0, 70, 70, pytest.approx(0.9), None, 1)]

    @pytest.mark.parametrize("frame", [None, np.zeros((0, 0, 3), dtype=np.uint8)])
    def test_an_empty_frame_yields_nothing_and_runs_no_inference(
        self, plugin: OpenVINOPlugin, frame: Any
    ) -> None:
        before = len(plugin.infer_request.inputs)
        assert plugin.detect(frame) == []
        assert len(plugin.infer_request.inputs) == before

    def test_scores_under_the_threshold_are_dropped(self, plugin: OpenVINOPlugin) -> None:
        plugin.compiled_model.queue_results(
            detection_tensor(
                [(100, 200, 40, 40, 0.24, 1), (400, 300, 40, 40, 0.26, 1)], num_classes=2
            )
        )
        assert plugin.detect(_frame()) == [(380, 200, 420, 240, pytest.approx(0.26), None, 1)]

    def test_a_threshold_override_applies_to_one_call_only(self, plugin: OpenVINOPlugin) -> None:
        plugin.compiled_model.queue_results(
            detection_tensor([(320, 320, 100, 80, 0.3, 1)], num_classes=2)
        )
        assert plugin.detect(_frame(), conf_threshold=0.5) == []
        assert plugin.conf_threshold == 0.25
        assert len(plugin.detect(_frame())) == 1

    def test_the_threshold_is_restored_when_inference_raises(self, plugin: OpenVINOPlugin) -> None:
        plugin.compiled_model.infer_error = RuntimeError("device lost")
        with pytest.raises(RuntimeError, match="device lost"):
            plugin.detect(_frame(), conf_threshold=0.9)
        assert plugin.conf_threshold == 0.25

    def test_overlapping_boxes_of_one_class_collapse_to_the_best(
        self, plugin: OpenVINOPlugin
    ) -> None:
        plugin.compiled_model.queue_results(
            detection_tensor(
                [(320, 320, 100, 80, 0.6, 1), (324, 320, 100, 80, 0.9, 1)], num_classes=2
            )
        )
        assert plugin.detect(_frame()) == [(274, 200, 374, 280, pytest.approx(0.9), None, 1)]

    def test_a_legacy_two_class_weight_suppresses_across_classes(
        self, plugin: OpenVINOPlugin
    ) -> None:
        plugin.compiled_model.queue_results(
            detection_tensor(
                [(320, 320, 100, 80, 0.6, 0), (324, 320, 100, 80, 0.9, 1)], num_classes=2
            )
        )
        assert [det[6] for det in plugin.detect(_frame())] == [1]

    def test_context_classes_keep_an_animal_inside_another_object(
        self, plugin: OpenVINOPlugin
    ) -> None:
        # The rat inside the start box: same place, different classes. Per-class
        # NMS must keep both (ADR-009).
        plugin.set_context_classes_present(True)
        plugin.compiled_model.queue_results(
            detection_tensor(
                [(320, 320, 100, 80, 0.6, 0), (324, 320, 100, 80, 0.9, 1)], num_classes=2
            )
        )
        assert sorted(det[6] for det in plugin.detect(_frame())) == [0, 1]

    def test_a_weight_with_more_than_two_classes_is_never_agnostic(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        directory = write_openvino_model_dir(tmp_path / "barnes", class_names=BARNES)
        barnes, backend = _build(
            monkeypatch, directory, backend=FakeOpenVINO(output_dims=((1, 7, 16),))
        )
        backend.compiled[-1].queue_results(
            detection_tensor(
                [(320, 320, 100, 80, 0.6, 1), (324, 320, 100, 80, 0.9, 2)], num_classes=3
            )
        )
        assert sorted(det[6] for det in barnes.detect(_frame())) == [1, 2]

    def test_detectors_announce_context_classes_to_the_plugin(self, plugin: OpenVINOPlugin) -> None:
        from zebtrack.core.detection.class_roles import resolve_class_role_map
        from zebtrack.core.detection.single_detector import SingleDetector

        plugin.class_names = {0: "rat", 1: "experimenter"}
        assert plugin._use_agnostic_nms() is True
        role_map = resolve_class_role_map(
            plugin.class_names,
            weight_entry={"class_roles": {"rat": "subject", "experimenter": "context"}},
        )

        SingleDetector(plugin=plugin, class_role_map=role_map)

        assert plugin._use_agnostic_nms() is False


class TestMasks:
    BOX = (320.0, 320.0, 200.0, 120.0, 0.9, 1)  # input x 220..420, y 260..380
    FRAME_BOX = (220, 260 - PAD_Y, 420, 380 - PAD_Y)

    def _seg_plugin(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> OpenVINOPlugin:
        directory = write_openvino_model_dir(tmp_path / "seg", class_names=ZEBRAFISH)
        built, backend = _build(monkeypatch, directory, backend=_seg_backend())
        backend.compiled[-1].queue_results(*_seg_tensors(self.BOX))
        return built

    def test_masks_are_not_decoded_unless_capture_is_on(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seg = self._seg_plugin(tmp_path, monkeypatch)
        calls: list[Any] = []
        real = module.process_mask

        def _spy(*args: Any, **kwargs: Any) -> Any:
            calls.append(args)
            return real(*args, **kwargs)

        monkeypatch.setattr(module, "process_mask", _spy)

        assert [det[:4] for det in seg.detect(_frame())] == [self.FRAME_BOX]
        assert calls == []
        assert seg.pop_frame_masks() == []

    def test_captured_contours_align_with_their_detection_in_frame_pixels(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seg = self._seg_plugin(tmp_path, monkeypatch)
        seg.set_mask_capture(True)

        detections = seg.detect(_frame())
        masks = seg.pop_frame_masks()

        assert [det[:4] for det in detections] == [self.FRAME_BOX]
        assert len(masks) == 1
        contour = masks[0]
        assert contour is not None
        assert contour.ndim == 2 and contour.shape[1] == 2
        x1, y1, x2, y2 = self.FRAME_BOX
        # The mask fills its box, so its outline IS the box, to resampling error.
        xs, ys = sorted(contour[:, 0].tolist()), sorted(contour[:, 1].tolist())
        assert xs[0] == pytest.approx(x1, abs=3)
        assert xs[-1] == pytest.approx(x2, abs=3)
        assert ys[0] == pytest.approx(y1, abs=3)
        assert ys[-1] == pytest.approx(y2, abs=3)

    def test_the_mask_buffer_is_consumed_by_reading_it(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seg = self._seg_plugin(tmp_path, monkeypatch)
        seg.set_mask_capture(True)
        seg.detect(_frame())
        assert len(seg.pop_frame_masks()) == 1
        # A second read must not hand the previous frame's masks to a new one.
        assert seg.pop_frame_masks() == []

    def test_a_frame_without_detections_leaves_no_masks(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seg = self._seg_plugin(tmp_path, monkeypatch)
        seg.set_mask_capture(True)
        seg.detect(_frame())
        seg.compiled_model.queue_results(
            np.zeros((1, 38, 16), dtype=np.float32), np.zeros((1, 32, 160, 160), dtype=np.float32)
        )
        seg.detect(_frame())  # consumes the first queued result
        assert seg.detect(_frame()) == []
        assert seg.pop_frame_masks() == []

    def test_a_mask_with_no_area_is_reported_as_none(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        directory = write_openvino_model_dir(tmp_path / "seg", class_names=ZEBRAFISH)
        seg, backend = _build(monkeypatch, directory, backend=_seg_backend())
        det, proto = _seg_tensors(self.BOX)
        proto[0, 0] = -10.0  # the mask is "off" everywhere
        backend.compiled[-1].queue_results(det, proto)
        seg.set_mask_capture(True)

        assert len(seg.detect(_frame())) == 1
        assert seg.pop_frame_masks() == [None]


class TestPredict:
    def test_detections_are_described_with_their_class_name(self, plugin: OpenVINOPlugin) -> None:
        plugin.compiled_model.queue_results(
            detection_tensor([(320, 320, 100, 80, 0.9, 1)], num_classes=2)
        )
        assert plugin.predict(_frame()) == [
            {
                "box": [270, 200, 370, 280],
                "confidence": pytest.approx(0.9),
                "class_id": 1,
                "class_name": "zebrafish",
                "has_mask": False,
                "mask_points": 0,
            }
        ]

    def test_the_diagnostic_always_decodes_masks(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        directory = write_openvino_model_dir(tmp_path / "seg", class_names=ZEBRAFISH)
        seg, backend = _build(monkeypatch, directory, backend=_seg_backend())
        backend.compiled[-1].queue_results(*_seg_tensors(TestMasks.BOX))

        (described,) = seg.predict(_frame())

        assert seg._capture_masks is False
        assert described["has_mask"] is True
        assert described["mask_points"] >= 4

    def test_the_threshold_override_is_scoped_to_the_call(self, plugin: OpenVINOPlugin) -> None:
        plugin.compiled_model.queue_results(
            detection_tensor([(320, 320, 100, 80, 0.3, 1)], num_classes=2)
        )
        assert plugin.predict(_frame(), conf_threshold=0.5) == []
        assert plugin.conf_threshold == 0.25
        assert len(plugin.predict(_frame())) == 1


# ---------------------------------------------------------------------------
# Batch inference through the async queue
# ---------------------------------------------------------------------------


def _queue_three(plugin: OpenVINOPlugin) -> list[tuple[int, int, int, int]]:
    """Queue three distinguishable results; return each one's box in the frame."""
    centres = [100, 300, 500]
    for cx in centres:
        plugin.compiled_model.queue_results(
            detection_tensor([(cx, 320, 40, 40, 0.9, 1)], num_classes=2)
        )
    return [(cx - 20, 300 - PAD_Y, cx + 20, 340 - PAD_Y) for cx in centres]


class TestDetectBatch:
    def test_no_frames_no_results(self, plugin: OpenVINOPlugin) -> None:
        assert plugin.detect_batch([]) == []

    def test_one_frame_skips_the_queue(self, plugin: OpenVINOPlugin) -> None:
        plugin.compiled_model.queue_results(
            detection_tensor([(320, 320, 100, 80, 0.9, 1)], num_classes=2)
        )
        assert plugin.detect_batch([_frame()]) == [
            [(270, 200, 370, 280, pytest.approx(0.9), None, 1)]
        ]
        assert not hasattr(plugin.compiled_model, "async_queues")

    def test_results_follow_frame_order_not_completion_order(self, plugin: OpenVINOPlugin) -> None:
        # The fake queue completes requests in reverse.
        boxes = _queue_three(plugin)
        results = plugin.detect_batch([_frame(), _frame(), _frame()])
        assert [[det[:4] for det in frame] for frame in results] == [[box] for box in boxes]

    def test_an_empty_frame_keeps_its_slot_and_is_not_submitted(
        self, plugin: OpenVINOPlugin
    ) -> None:
        boxes = _queue_three(plugin)
        results = plugin.detect_batch([_frame(), np.zeros((0, 0, 3), dtype=np.uint8), _frame()])

        (queue,) = plugin.compiled_model.async_queues
        assert queue.submitted == [0, 2]
        assert [[det[:4] for det in frame] for frame in results] == [[boxes[0]], [], [boxes[1]]]

    @pytest.mark.parametrize(
        ("batch_nireq", "frames", "expected_jobs"),
        [(8, 3, 3), (2, 3, 2), (0, 3, 1)],
    )
    def test_the_request_pool_is_capped_by_the_frame_count(
        self,
        model_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
        batch_nireq: int,
        frames: int,
        expected_jobs: int,
    ) -> None:
        built, _backend = _build(
            monkeypatch, model_dir, settings_obj=openvino_settings(batch_nireq=batch_nireq)
        )
        built.compiled_model.queue_results(detection_tensor([], num_classes=2))
        built.detect_batch([_frame() for _ in range(frames)])
        (queue,) = built.compiled_model.async_queues
        assert queue.jobs == expected_jobs

    @pytest.mark.parametrize(
        ("memory_mode", "expected_jobs"),
        [("low", 1), ("normal", 3)],
    )
    def test_low_memory_mode_keeps_one_request_whatever_batch_nireq_says(
        self,
        model_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
        memory_mode: str,
        expected_jobs: int,
    ) -> None:
        """#725: memory_mode="low" is enforced by the reader of batch_nireq."""
        settings_obj = openvino_settings(batch_nireq=8)
        settings_obj.performance = SimpleNamespace(memory_mode=memory_mode)
        built, _backend = _build(monkeypatch, model_dir, settings_obj=settings_obj)
        built.compiled_model.queue_results(detection_tensor([], num_classes=2))
        built.detect_batch([_frame() for _ in range(3)])
        (queue,) = built.compiled_model.async_queues
        assert queue.jobs == expected_jobs

    def test_without_settings_four_requests_are_used(self, plugin: OpenVINOPlugin) -> None:
        plugin.compiled_model.queue_results(detection_tensor([], num_classes=2))
        plugin.detect_batch([_frame() for _ in range(6)])
        (queue,) = plugin.compiled_model.async_queues
        assert queue.jobs == 4

    def test_a_queue_failure_falls_back_to_sequential_inference(
        self, model_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        backend = FakeOpenVINO()
        backend.async_queue_error = RuntimeError("no async support")
        built, _backend = _build(monkeypatch, model_dir, backend=backend)
        boxes = _queue_three(built)

        results = built.detect_batch([_frame(), _frame(), _frame()], conf_threshold=0.5)

        assert [[det[:4] for det in frame] for frame in results] == [[box] for box in boxes]
        assert built.conf_threshold == 0.25

    def test_the_threshold_override_reaches_the_batch(self, plugin: OpenVINOPlugin) -> None:
        plugin.compiled_model.queue_results(
            detection_tensor([(320, 320, 100, 80, 0.3, 1)], num_classes=2)
        )
        assert plugin.detect_batch([_frame(), _frame()], conf_threshold=0.5) == [[], []]
        assert plugin.conf_threshold == 0.25
        assert [len(frame) for frame in plugin.detect_batch([_frame(), _frame()])] == [1, 1]

    def test_a_batch_never_leaves_one_frames_masks_behind(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        directory = write_openvino_model_dir(tmp_path / "seg", class_names=ZEBRAFISH)
        seg, backend = _build(monkeypatch, directory, backend=_seg_backend())
        backend.compiled[-1].queue_results(*_seg_tensors(TestMasks.BOX))
        seg.set_mask_capture(True)
        seg.detect(_frame())  # leaves one frame's masks in the buffer

        results = seg.detect_batch([_frame(), _frame()])

        assert [len(frame) for frame in results] == [1, 1]
        # Masks of ONE frame cannot be attributed to a batch: none is better than wrong.
        assert seg.pop_frame_masks() == []

    def test_a_request_that_never_completes_yields_an_empty_frame(
        self, plugin: OpenVINOPlugin, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class _LossyQueue:
            def __init__(self, compiled: Any, jobs: int) -> None:
                self._callback: Any = None
                self._compiled = compiled
                self._done: list[int] = []

            def set_callback(self, callback: Any) -> None:
                self._callback = callback

            def start_async(self, inputs: dict[str, Any], userdata: int) -> None:
                if userdata != 1:  # frame 1 is lost
                    self._done.append(userdata)

            def wait_all(self) -> None:
                for userdata in self._done:
                    self._callback(MagicMock(results=self._compiled.next_results()), userdata)

        monkeypatch.setattr(module.ov, "AsyncInferQueue", _LossyQueue, raising=False)
        plugin.compiled_model.queue_results(
            detection_tensor([(320, 320, 100, 80, 0.9, 1)], num_classes=2)
        )

        results = plugin.detect_batch([_frame(), _frame(), _frame()])

        assert [len(frame) for frame in results] == [1, 0, 1]
