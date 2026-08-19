"""Extended unit tests for core/services/weight_manager.py."""

from __future__ import annotations

from pathlib import Path

from zebtrack.core.services.weight_manager import (
    OPENVINO_STATUS_CONVERTING,
    OPENVINO_STATUS_FAILED,
    OPENVINO_STATUS_NOT_CONVERTED,
    OPENVINO_STATUS_READY,
    TARGET_AQUARIUM,
    TARGET_ZEBRAFISH,
    VALID_METHODS,
    VALID_TARGETS,
    OpenVINOExportError,
    WeightManager,
    _default_flag_key,
)


class TestWeightManagerTaxonomyAndExceptions:
    """Test weight targets, flag keys, and OpenVINOExportError."""

    def test_default_flag_key(self):
        assert _default_flag_key("det", "aquarium") == "is_default_det_aquarium"
        assert _default_flag_key("seg", "zebrafish") == "is_default_seg_zebrafish"

    def test_constants(self):
        assert TARGET_AQUARIUM == "aquarium"
        assert TARGET_ZEBRAFISH == "zebrafish"
        assert "seg" in VALID_METHODS
        assert "det" in VALID_METHODS
        assert "aquarium" in VALID_TARGETS
        assert "zebrafish" in VALID_TARGETS
        assert OPENVINO_STATUS_NOT_CONVERTED == "not_converted"
        assert OPENVINO_STATUS_CONVERTING == "converting"
        assert OPENVINO_STATUS_READY == "ready"
        assert OPENVINO_STATUS_FAILED == "failed"

    def test_openvino_export_error_attributes(self):
        cause = RuntimeError("ultralytics export failed")
        err = OpenVINOExportError(
            message="Export crashed",
            weight_name="yolo11n-seg",
            model_path="/weights/m.pt",
            cause=cause,
        )
        assert str(err) == "Export crashed"
        assert err.weight_name == "yolo11n-seg"
        assert err.model_path == Path("/weights/m.pt")
        assert err.cause is cause


class TestWeightManagerClassificationAndLookup:
    """Test classification, normalization, overrides, and resolution."""

    def test_classify_weight_type(self, tmp_path: Path):
        wm = WeightManager(config_dir=tmp_path, weights_dir=tmp_path / "w")
        assert wm._classify_weight_type("best_seg_lateral.pt") == "seg"
        assert wm._classify_weight_type("best_det_topdown.pt") == "det"
        assert wm._classify_weight_type("yolo11_seg.pt") == "seg"
        assert wm._classify_weight_type("yolo11_oi.pt") == "det"
        assert wm._classify_weight_type("unclassified.pt") is None

    def test_classify_perspective(self, tmp_path: Path):
        wm = WeightManager(config_dir=tmp_path, weights_dir=tmp_path / "w")
        assert wm._classify_perspective("model_lateral.pt") == "lateral"
        assert wm._classify_perspective("model_topdown.pt") == "top_down"
        assert wm._classify_perspective("model_plain.pt") is None

    def test_normalize_target_alias(self):
        assert WeightManager._normalize_target_alias("fish") == TARGET_ZEBRAFISH
        assert WeightManager._normalize_target_alias("animal") == TARGET_ZEBRAFISH
        assert WeightManager._normalize_target_alias("zebrafish") == TARGET_ZEBRAFISH
        assert WeightManager._normalize_target_alias("aquarium") == TARGET_AQUARIUM
        assert WeightManager._normalize_target_alias("tank") == TARGET_AQUARIUM
        assert WeightManager._normalize_target_alias("aquario") == TARGET_AQUARIUM
        assert WeightManager._normalize_target_alias("invalid") is None
        assert WeightManager._normalize_target_alias(None) is None
        assert WeightManager._normalize_target_alias("") is None

    def test_get_all_weights_and_details(self, tmp_path: Path):
        wm = WeightManager(config_dir=tmp_path, weights_dir=tmp_path / "w")
        wm.weights["custom_weight"] = {
            "path": "/weights/custom.pt",
            "type": "seg",
            "target": "zebrafish",
            "perspective": "lateral",
            "is_default": True,
            "is_default_seg": True,
        }

        all_weights = wm.get_all_weights()
        assert "custom_weight" in all_weights

        details = wm.get_weight_details("custom_weight")
        assert details is not None
        assert details["perspective"] == "lateral"

        assert wm.get_weight_details("non_existent") is None

    def test_get_default_weights(self, tmp_path: Path):
        wm = WeightManager(config_dir=tmp_path, weights_dir=tmp_path / "w")
        wm.weights["fish_seg"] = {
            "path": "/weights/fish_seg.pt",
            "type": "seg",
            "target": "zebrafish",
            "is_default": True,
            "is_default_seg": True,
        }
        wm.weights["tank_det"] = {
            "path": "/weights/tank_det.pt",
            "type": "det",
            "target": "aquarium",
            "is_default": False,
            "is_default_det": True,
        }

        name, details = wm.get_default_weight()
        assert name == "fish_seg"

        seg_name, _ = wm.get_default_seg_weight()
        assert seg_name == "fish_seg"

        det_name, _ = wm.get_default_det_weight()
        assert det_name == "tank_det"

    def test_get_weight_by_perspective_and_type(self, tmp_path: Path):
        wm = WeightManager(config_dir=tmp_path, weights_dir=tmp_path / "w")
        wm.weights["fish_lateral"] = {
            "path": "/weights/fish_lateral.pt",
            "type": "seg",
            "perspective": "lateral",
        }
        wm.weights["fish_topdown"] = {
            "path": "/weights/fish_topdown.pt",
            "type": "seg",
            "perspective": "top_down",
        }

        name, _ = wm.get_weight_by_perspective_and_type("lateral", "seg")
        assert name == "fish_lateral"

        name2, _ = wm.get_weight_by_perspective_and_type("top_down", "seg")
        assert name2 == "fish_topdown"

        # Fallback when perspective doesn't match
        name_fb, _ = wm.get_weight_by_perspective_and_type("unknown_perspective", "seg")
        assert name_fb in ("fish_lateral", "fish_topdown")

        # No match for non-existent type
        no_match, _ = wm.get_weight_by_perspective_and_type("lateral", "det")
        assert no_match is None

    def test_get_weight_path_by_method_invalid(self, tmp_path: Path):
        wm = WeightManager(config_dir=tmp_path, weights_dir=tmp_path / "w")
        assert wm.get_weight_path_by_method("invalid_method", "fish") is None
        assert wm.get_weight_path_by_method("seg", "unknown_task") is None
