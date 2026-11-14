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


# ---------------------------------------------------------------------------
# NMS per class (ADR-009): agnostic only for the legacy two-class weights.
# ---------------------------------------------------------------------------


def _nms_plugin(class_names: dict[int, str]) -> OpenVINOPlugin:
    """A plugin shell whose ``_postprocess`` can run without a compiled model.

    ``object.__new__`` because the real constructor compiles an OpenVINO model;
    the method under test (``_postprocess``) is driven for real.
    """
    plugin = object.__new__(OpenVINOPlugin)
    plugin.class_names = dict(class_names)
    plugin.conf_threshold = 0.25
    plugin.nms_threshold = 0.45
    plugin.output_det = "det"
    plugin.output_proto = None
    return plugin


@pytest.mark.skipif(not TORCH_AVAILABLE, reason="torch is required by the NMS path")
class TestPerClassNms:
    def _agnostic_flag(self, plugin: OpenVINOPlugin, monkeypatch) -> bool:
        import torch

        from zebtrack.plugins import openvino_detector as module

        seen: dict[str, bool] = {}

        def _fake_nms(**kwargs):
            seen["agnostic"] = kwargs["agnostic"]
            return [torch.zeros((0, 6))]

        monkeypatch.setattr(module, "non_max_suppression", _fake_nms)
        detections, _masks = plugin._postprocess(
            {"det": np.zeros((1, 6, 10), dtype=np.float32)}, (480, 640, 3), (640, 640)
        )
        assert len(detections) == 0
        return seen["agnostic"]

    def test_legacy_two_class_weight_keeps_agnostic_nms(self, monkeypatch):
        plugin = _nms_plugin({0: "aqua", 1: "zebrafish"})
        assert self._agnostic_flag(plugin, monkeypatch) is True

    def test_more_than_two_classes_use_per_class_nms(self, monkeypatch):
        plugin = _nms_plugin({0: "arena", 1: "experimenter", 2: "rat"})
        assert self._agnostic_flag(plugin, monkeypatch) is False

    def test_context_roles_force_per_class_nms_on_two_classes(self, monkeypatch):
        plugin = _nms_plugin({0: "rat", 1: "experimenter"})
        plugin.set_context_classes_present(True)
        assert self._agnostic_flag(plugin, monkeypatch) is False

    def test_detectors_announce_context_classes_to_the_plugin(self):
        from unittest.mock import MagicMock

        from zebtrack.core.detection.class_roles import resolve_class_role_map
        from zebtrack.core.detection.single_detector import SingleDetector

        plugin = _nms_plugin({0: "rat", 1: "experimenter"})
        plugin.get_name = MagicMock(return_value="OpenVINO")  # type: ignore[method-assign]
        role_map = resolve_class_role_map(
            plugin.class_names,
            weight_entry={"class_roles": {"rat": "subject", "experimenter": "context"}},
        )

        SingleDetector(plugin=plugin, class_role_map=role_map)

        assert plugin._use_agnostic_nms() is False
