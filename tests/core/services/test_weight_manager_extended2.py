"""Extended unit tests for core/services/weight_manager.py."""

from __future__ import annotations

from pathlib import Path

from zebtrack.core.services.weight_manager import (
    DEFAULT_WEIGHTS_DIR,
    OPENVINO_CACHE_DIR,
    OPENVINO_STATUS_CONVERTING,
    OPENVINO_STATUS_FAILED,
    OPENVINO_STATUS_NOT_CONVERTED,
    OPENVINO_STATUS_READY,
    TARGET_AQUARIUM,
    TARGET_ZEBRAFISH,
    VALID_METHODS,
    VALID_TARGETS,
    WEIGHTS_CONFIG_FILE,
    OpenVINOExportError,
    WeightManager,
    _default_flag_key,
    _default_target_for_type,
)


class TestWeightManagerExtended2:
    """Test WeightManager constants, classifications, default target helpers, and overrides."""

    def test_constants_and_targets(self):
        assert WEIGHTS_CONFIG_FILE == "weights_config.json"
        assert OPENVINO_CACHE_DIR == "openvino_model_cache"
        assert DEFAULT_WEIGHTS_DIR == "weights"

        assert TARGET_AQUARIUM == "aquarium"
        assert TARGET_ZEBRAFISH == "zebrafish"
        assert "aquarium" in VALID_TARGETS
        assert "zebrafish" in VALID_TARGETS
        assert "seg" in VALID_METHODS
        assert "det" in VALID_METHODS

    def test_openvino_status_constants(self):
        assert OPENVINO_STATUS_NOT_CONVERTED == "not_converted"
        assert OPENVINO_STATUS_CONVERTING == "converting"
        assert OPENVINO_STATUS_READY == "ready"
        assert OPENVINO_STATUS_FAILED == "failed"

    def test_default_target_for_type(self):
        assert _default_target_for_type("seg") == TARGET_ZEBRAFISH
        assert _default_target_for_type("det") == TARGET_AQUARIUM
        assert _default_target_for_type("other") == TARGET_AQUARIUM

    def test_default_flag_key(self):
        assert _default_flag_key("seg", "zebrafish") == "is_default_seg_zebrafish"
        assert _default_flag_key("det", "aquarium") == "is_default_det_aquarium"

    def test_openvino_export_error(self):
        cause = ValueError("Model file corrupted")
        err = OpenVINOExportError(
            message="Export failed",
            weight_name="yolo11n",
            model_path=Path("/path/yolo11n.pt"),
            cause=cause,
        )
        assert str(err) == "Export failed"
        assert err.weight_name == "yolo11n"
        assert err.model_path == Path("/path/yolo11n.pt")
        assert err.cause is cause

    def test_resolve_weights_dir(self, tmp_path: Path):
        wm = WeightManager(config_dir=tmp_path)
        # Default relative to config_dir
        assert wm.weights_dir == str(tmp_path / "weights")

        # Explicit absolute override
        custom_dir = tmp_path / "custom_weights"
        resolved = wm._resolve_weights_dir(custom_dir)
        assert resolved == custom_dir

    def test_runtime_slot_overrides(self, tmp_path: Path):
        wm = WeightManager(config_dir=tmp_path)
        wm._runtime_slot_overrides[("seg", "zebrafish")] = "custom_seg.pt"

        assert wm._runtime_slot_overrides.get(("seg", "zebrafish")) == "custom_seg.pt"
        assert wm._runtime_slot_overrides.get(("det", "aquarium")) is None

    def test_classify_weight_type(self, tmp_path: Path):
        wm = WeightManager(config_dir=tmp_path)
        assert wm._classify_weight_type("model_seg_lateral.pt") == "seg"
        assert wm._classify_weight_type("best_seg_topdown.pt") == "seg"
        assert wm._classify_weight_type("legacy_seg.pt") == "seg"
        assert wm._classify_weight_type("model_det_lateral.pt") == "det"
        assert wm._classify_weight_type("best_det_topdown.pt") == "det"
        assert wm._classify_weight_type("legacy_oi.pt") == "det"
        assert wm._classify_weight_type("unknown_model.pt") is None

    def test_classify_perspective(self, tmp_path: Path):
        wm = WeightManager(config_dir=tmp_path)
        assert wm._classify_perspective("yolo_lateral.pt") == "lateral"
        assert wm._classify_perspective("yolo_topdown.pt") == "top_down"
        assert wm._classify_perspective("generic_yolo.pt") is None

    def test_normalize_target_alias(self):
        assert WeightManager._normalize_target_alias("animal") == TARGET_ZEBRAFISH
        assert WeightManager._normalize_target_alias("fish") == TARGET_ZEBRAFISH
        assert WeightManager._normalize_target_alias("zebrafish") == TARGET_ZEBRAFISH
        assert WeightManager._normalize_target_alias("aquarium") == TARGET_AQUARIUM
        assert WeightManager._normalize_target_alias("aquario") == TARGET_AQUARIUM
        assert WeightManager._normalize_target_alias("tank") == TARGET_AQUARIUM
        assert WeightManager._normalize_target_alias("") is None
        assert WeightManager._normalize_target_alias(None) is None
