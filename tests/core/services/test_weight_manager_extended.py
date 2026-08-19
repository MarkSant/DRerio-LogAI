"""
Extended unit tests for WeightManager in core/services/weight_manager.py.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

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
from zebtrack.settings import load_settings


class TestWeightManagerExtended:
    def _create_weight_manager(self, tmp_path: Path) -> WeightManager:
        settings = load_settings()
        (tmp_path / "weights").mkdir(parents=True, exist_ok=True)
        return WeightManager(
            settings_obj=settings,
            config_dir=tmp_path,
            weights_dir=tmp_path / "weights",
        )

    def test_get_weight_by_perspective_and_type(self, tmp_path: Path):
        wm = self._create_weight_manager(tmp_path)
        wm.weights = {
            "top_seg.pt": {"type": "seg", "perspective": "top_down"},
            "lat_seg.pt": {"type": "seg", "perspective": "lateral"},
            "top_det.pt": {"type": "det", "perspective": "top_down"},
        }

        # Exact match
        name, details = wm.get_weight_by_perspective_and_type("lateral", "seg")
        assert name == "lat_seg.pt"

        # Fallback match (requested lateral det, but only top_down det exists)
        name, details = wm.get_weight_by_perspective_and_type("lateral", "det")
        assert name == "top_det.pt"

        # No match for type
        name, details = wm.get_weight_by_perspective_and_type("lateral", "pose")
        assert name is None
        assert details is None

    def test_set_default_weight_by_type(self, tmp_path: Path):
        wm = self._create_weight_manager(tmp_path)
        wm.weights = {
            "seg1.pt": {"type": "seg", "target": "zebrafish"},
            "det1.pt": {"type": "det", "target": "eyes"},
        }
        wm.set_default_weight_for = MagicMock()  # type: ignore[method-assign]

        # Not found
        wm.set_default_weight_by_type("unknown.pt", "seg")
        wm.set_default_weight_for.assert_not_called()

        # Type mismatch
        wm.set_default_weight_by_type("det1.pt", "seg")
        wm.set_default_weight_for.assert_not_called()

        # Success
        wm.set_default_weight_by_type("seg1.pt", "seg")
        wm.set_default_weight_for.assert_called_once_with(
            "seg1.pt", method="seg", target="zebrafish"
        )

    def test_set_default_weight(self, tmp_path: Path):
        wm = self._create_weight_manager(tmp_path)
        wm.weights = {
            "seg1.pt": {"type": "seg", "is_default": False, "is_default_seg": False},
            "det1.pt": {"type": "det", "is_default": False, "is_default_det": False},
            "unknown.pt": {"type": "other"},
        }
        wm.save_weights = MagicMock()  # type: ignore[method-assign]

        # Not found
        assert wm.set_default_weight("missing.pt") is False

        # Unknown type
        assert wm.set_default_weight("unknown.pt") is False

        # Set seg default
        assert wm.set_default_weight("seg1.pt") is True
        assert wm.weights["seg1.pt"]["is_default"] is True
        assert wm.weights["seg1.pt"]["is_default_seg"] is True
        wm.save_weights.assert_called_once()

        # Set det default
        assert wm.set_default_weight("det1.pt") is True
        assert wm.weights["det1.pt"]["is_default"] is True
        assert wm.weights["det1.pt"]["is_default_det"] is True
        assert wm.weights["seg1.pt"]["is_default"] is False

    def test_resolve_weight_filename(self, tmp_path: Path):
        wm = self._create_weight_manager(tmp_path)

        # Bare filename
        resolved = wm._resolve_weight_filename("model.pt")
        assert resolved == str(Path(wm.weights_dir) / "model.pt")

        # Absolute filename
        abs_path = str(tmp_path / "custom" / "model.pt")
        assert wm._resolve_weight_filename(abs_path) == abs_path

    def test_clear_runtime_slot_overrides(self, tmp_path: Path):
        wm = self._create_weight_manager(tmp_path)
        wm._runtime_slot_overrides = {("seg", "zebrafish"): "runtime.pt"}
        wm.clear_runtime_slot_overrides()
        assert wm._runtime_slot_overrides == {}

    def test_default_target_for_type(self):
        assert _default_target_for_type("seg") == TARGET_ZEBRAFISH
        assert _default_target_for_type("det") == TARGET_AQUARIUM
        assert _default_target_for_type("other") == TARGET_AQUARIUM

    def test_default_flag_key(self):
        assert _default_flag_key("seg", "zebrafish") == "is_default_seg_zebrafish"
        assert _default_flag_key("det", "aquarium") == "is_default_det_aquarium"

    def test_openvino_export_error(self):
        cause_err = RuntimeError("Export sub-error")
        err = OpenVINOExportError(
            message="Export failed",
            weight_name="model.pt",
            model_path=Path("/tmp/model.pt"),
            cause=cause_err,
        )
        assert str(err) == "Export failed"
        assert err.weight_name == "model.pt"
        assert err.model_path == Path("/tmp/model.pt")
        assert err.cause is cause_err

    def test_resolve_weights_dir_custom(self, tmp_path: Path):
        settings = load_settings()
        mgr_custom = WeightManager(
            settings_obj=settings,
            config_dir=tmp_path,
            weights_dir=tmp_path / "custom_weights",
        )
        assert Path(mgr_custom.weights_dir) == tmp_path / "custom_weights"
        assert (tmp_path / "custom_weights").exists()

    def test_load_and_migrate_legacy_weights(self, tmp_path: Path):
        settings = load_settings()
        config_file = tmp_path / "weights_config.json"
        legacy_data = {
            "legacy_seg.pt": {
                "path": str(tmp_path / "weights" / "legacy_seg.pt"),
                "is_default": True,
            },
            "legacy_det.pt": {
                "path": str(tmp_path / "weights" / "legacy_det.pt"),
                "is_default": False,
            },
        }
        config_file.write_text(json.dumps(legacy_data), encoding="utf-8")

        mgr = WeightManager(settings_obj=settings, config_dir=tmp_path)
        assert "legacy_seg.pt" in mgr.weights
        assert mgr.weights["legacy_seg.pt"]["type"] == "seg"
        assert mgr.weights["legacy_seg.pt"]["target"] == TARGET_ZEBRAFISH
        assert mgr.weights["legacy_seg.pt"]["is_default_seg_zebrafish"] is True
        assert mgr.weights["legacy_seg.pt"]["openvino_status"] == OPENVINO_STATUS_NOT_CONVERTED

    def test_classify_weight_type_and_perspective(self, tmp_path: Path):
        wm = self._create_weight_manager(tmp_path)
        assert wm._classify_weight_type("best_seg.pt") == "seg"
        assert wm._classify_weight_type("best_det.pt") == "det"
        assert wm._classify_weight_type("model_seg.pt") == "seg"
        assert wm._classify_weight_type("model_oi.pt") == "det"
        assert wm._classify_weight_type("custom_unknown.pt") is None

        assert wm._classify_perspective("best_lateral.pt") == "lateral"
        assert wm._classify_perspective("best_topdown.pt") == "top_down"
        assert wm._classify_perspective("generic_model.pt") is None

    def test_get_and_set_default_weight_for(self, tmp_path: Path):
        wm = self._create_weight_manager(tmp_path)
        wm.weights = {
            "seg1.pt": {
                "path": "/path/seg1.pt",
                "type": "seg",
                "target": "zebrafish",
                "is_default_seg_zebrafish": True,
            },
            "seg2.pt": {
                "path": "/path/seg2.pt",
                "type": "seg",
                "target": "zebrafish",
                "is_default_seg_zebrafish": False,
            },
        }
        name, meta = wm.get_default_weight_for("seg", "zebrafish")
        assert name == "seg1.pt"
        assert meta is not None


class TestWeightManagerExtended2:
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


class TestWeightManagerTaxonomyAndExceptions:
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


class TestWeightManagerExtended4:
    def test_classify_weight_type_perspective_aware(self):
        wm = object.__new__(WeightManager)

        assert wm._classify_weight_type("best_seg_lateral.pt") == "seg"
        assert wm._classify_weight_type("best_seg_topdown.pt") == "seg"
        assert wm._classify_weight_type("best_det_lateral.pt") == "det"
        assert wm._classify_weight_type("best_det_topdown.pt") == "det"

    def test_classify_weight_type_legacy(self):
        wm = object.__new__(WeightManager)

        assert wm._classify_weight_type("model_seg.pt") == "seg"
        assert wm._classify_weight_type("model_oi.pt") == "det"
        assert wm._classify_weight_type("unknown_model.pt") is None

    def test_classify_perspective(self):
        wm = object.__new__(WeightManager)

        assert wm._classify_perspective("best_seg_lateral.pt") == "lateral"
        assert wm._classify_perspective("best_det_topdown.pt") == "top_down"
        assert wm._classify_perspective("generic_weights.pt") is None


class TestWeightManagerExtended5:
    def test_resolve_weights_dir_override(self, tmp_path: Path):
        override_dir = tmp_path / "custom_weights"
        wm = WeightManager(settings_obj=None, config_dir=tmp_path, weights_dir=override_dir)
        assert Path(wm.weights_dir) == override_dir

    def test_resolve_weights_dir_relative(self, tmp_path: Path):
        wm = WeightManager(settings_obj=None, config_dir=tmp_path, weights_dir="rel_weights")
        assert Path(wm.weights_dir) == tmp_path / "rel_weights"

    def test_runtime_slot_overrides_initial_state(self, tmp_path: Path):
        wm = WeightManager(settings_obj=None, config_dir=tmp_path)
        assert wm._runtime_slot_overrides == {}

    def test_set_runtime_slot_overrides(self, tmp_path: Path):
        wm = WeightManager(settings_obj=None, config_dir=tmp_path)
        wm.weights["custom_seg.pt"] = {
            "type": "seg",
            "target": "zebrafish",
            "path": "/path/custom_seg.pt",
        }

        overrides: dict[tuple[str, str], str | None] = {("seg", "zebrafish"): "custom_seg.pt"}
        wm.set_runtime_slot_overrides(overrides)
        assert wm._runtime_slot_overrides == overrides


class TestWeightManagerExtended6:
    def test_resolve_weight_filename_bare_name(self, tmp_path: Path):
        wm = WeightManager(settings_obj=None, config_dir=tmp_path, weights_dir=tmp_path / "weights")
        resolved = wm._resolve_weight_filename("custom.pt")
        assert resolved == str(tmp_path / "weights" / "custom.pt")

    def test_resolve_weight_filename_absolute(self, tmp_path: Path):
        wm = WeightManager(settings_obj=None, config_dir=tmp_path, weights_dir=tmp_path / "weights")
        abs_path = tmp_path / "other_dir" / "model.pt"
        resolved = wm._resolve_weight_filename(str(abs_path))
        assert resolved == str(abs_path)

    def test_resolve_weight_filename_with_subdir(self, tmp_path: Path):
        wm = WeightManager(settings_obj=None, config_dir=tmp_path, weights_dir=tmp_path / "weights")
        rel_sub = "subfolder/model.pt"
        resolved = wm._resolve_weight_filename(rel_sub)
        assert Path(resolved) == Path(rel_sub)


class TestWeightManagerExtended7:
    def test_add_weight_not_found(self, tmp_path: Path):
        wm = WeightManager(settings_obj=None, config_dir=tmp_path)
        missing_path = tmp_path / "missing_model.pt"

        with pytest.raises(FileNotFoundError, match="model file was not found"):
            wm.add_weight(missing_path, set_as_default=False)

    def test_add_weight_already_registered(self, tmp_path: Path):
        weights_dir = tmp_path / "weights"
        weights_dir.mkdir()
        model_file = weights_dir / "existing.pt"
        model_file.touch()

        wm = WeightManager(settings_obj=None, config_dir=tmp_path, weights_dir=weights_dir)
        wm.weights["existing.pt"] = {"type": "det", "path": str(model_file)}

        with pytest.raises(ValueError, match="already exists"):
            wm.add_weight(model_file, set_as_default=False)

    def test_classify_weight_type_heuristics(self, tmp_path: Path):
        wm = WeightManager(settings_obj=None, config_dir=tmp_path)
        assert wm._classify_weight_type("best_seg.pt") == "seg"
        assert wm._classify_weight_type("model_seg_lateral.pt") == "seg"
        assert wm._classify_weight_type("model_seg.pt") == "seg"
        assert wm._classify_weight_type("best_det.pt") == "det"
        assert wm._classify_weight_type("model_det_topdown.pt") == "det"
        assert wm._classify_weight_type("model_oi.pt") == "det"
        assert wm._classify_weight_type("random_model.pt") is None

    def test_classify_perspective_heuristics(self, tmp_path: Path):
        wm = WeightManager(settings_obj=None, config_dir=tmp_path)
        assert wm._classify_perspective("model_seg_lateral.pt") == "lateral"
        assert wm._classify_perspective("model_det_topdown.pt") == "top_down"
        assert wm._classify_perspective("generic_model.pt") is None


class TestWeightManagerExtended8:
    def test_maybe_relocate_path_empty_name(self):
        wm = object.__new__(WeightManager)
        assert wm._maybe_relocate_path("", "/some/path") is None

    def test_maybe_relocate_path_target_does_not_exist(self, tmp_path: Path):
        wm = object.__new__(WeightManager)
        wm.weights_dir = str(tmp_path)
        assert wm._maybe_relocate_path("missing.pt", "/old/path/missing.pt") is None

    def test_maybe_relocate_path_success(self, tmp_path: Path):
        wm = object.__new__(WeightManager)
        wm.weights_dir = str(tmp_path)
        target_file = tmp_path / "model.pt"
        target_file.touch()

        old_path = tmp_path / "nonexistent_dir" / "model.pt"
        relocated = wm._maybe_relocate_path("model.pt", old_path)
        assert relocated == str(target_file.resolve())

    def test_initialize_default_weight_no_settings(self):
        wm = object.__new__(WeightManager)
        wm.settings = None
        wm._initialize_default_weight()

    def test_get_all_weights_empty(self):
        wm = object.__new__(WeightManager)
        wm.weights = {}
        assert wm.get_all_weights() == []

    def test_get_weight_details_found_and_not_found(self):
        wm = object.__new__(WeightManager)
        wm.weights = {"fish.pt": {"path": "/models/fish.pt", "type": "det"}}

        details = wm.get_weight_details("fish.pt")
        assert details == {"path": "/models/fish.pt", "type": "det"}

        missing = wm.get_weight_details("nonexistent.pt")
        assert missing is None


class TestWeightManagerExtended9:
    def test_set_runtime_slot_overrides_stores_dict(self):
        wm = object.__new__(WeightManager)
        wm._runtime_slot_overrides = {}
        wm.weights = {
            "new_fish.pt": {"type": "det"},
            "new_arena.pt": {"type": "seg"},
        }

        overrides: dict[tuple[str, str], str | None] = {
            ("det", "zebrafish"): "new_fish.pt",
            ("seg", "aquarium"): "new_arena.pt",
        }
        wm.set_runtime_slot_overrides(overrides)

        assert wm._runtime_slot_overrides == overrides

    def test_clear_runtime_slot_overrides(self):
        wm = object.__new__(WeightManager)
        wm._runtime_slot_overrides = {("det", "zebrafish"): "custom.pt"}

        wm.clear_runtime_slot_overrides()
        assert wm._runtime_slot_overrides == {}


class TestWeightManagerExtended11:
    def test_target_taxonomy_constants(self):
        assert TARGET_AQUARIUM == "aquarium"
        assert TARGET_ZEBRAFISH == "zebrafish"
        assert VALID_TARGETS == ("aquarium", "zebrafish")
        assert VALID_METHODS == ("seg", "det")

    def test_weight_manager_init(self):
        mgr = WeightManager(settings_obj=None)
        assert isinstance(mgr, WeightManager)
