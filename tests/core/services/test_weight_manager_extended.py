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


class TestPerspectiveIsAHardConstraint:
    """A requested perspective must outrank the perspective-blind slot default.

    Regression cover for 2026-09-05. ``_default_target_for_type`` gives every
    weight a single target from its TYPE ("seg tracks the fish, det tracks the
    tank" — the v3.x convention), so today's dual-class weights can never be
    registered under ``(seg, aquarium)``. Arena detection asks for exactly that,
    the lookup landed on ``is_default_seg_aquarium`` — a flag a LATERAL weight
    legitimately carries — and a top-down plus-maze video was segmented with the
    lateral model: 88% of the frame instead of the maze.
    """

    def _manager(self, tmp_path: Path) -> WeightManager:
        wm = WeightManager(settings_obj=None, config_dir=tmp_path, weights_dir=tmp_path)
        wm.weights = {
            "best_seg_lateral.pt": {
                "path": "/w/best_seg_lateral.pt",
                "type": "seg",
                "target": TARGET_ZEBRAFISH,
                "perspective": "lateral",
                # The slot flag that used to win regardless of perspective.
                "is_default_seg_aquarium": True,
                "is_default_seg": True,
            },
            "best_seg_topdown.pt": {
                "path": "/w/best_seg_topdown.pt",
                "type": "seg",
                "target": TARGET_ZEBRAFISH,
                "perspective": "top_down",
            },
        }
        return wm

    def test_top_down_request_does_not_return_the_lateral_default(self, tmp_path: Path):
        wm = self._manager(tmp_path)

        path = wm.get_weight_path_by_method(method="seg", task="aquarium", perspective="top_down")

        assert path == "/w/best_seg_topdown.pt"

    def test_lateral_request_still_returns_the_lateral_weight(self, tmp_path: Path):
        wm = self._manager(tmp_path)

        path = wm.get_weight_path_by_method(method="seg", task="aquarium", perspective="lateral")

        assert path == "/w/best_seg_lateral.pt"

    def test_no_perspective_requested_keeps_the_slot_default(self, tmp_path: Path):
        """Unchanged behaviour when the caller expresses no preference."""
        wm = self._manager(tmp_path)

        path = wm.get_weight_path_by_method(method="seg", task="aquarium", perspective=None)

        assert path == "/w/best_seg_lateral.pt"

    def test_runtime_override_still_wins_over_perspective(self, tmp_path: Path):
        """An explicit user override is a deliberate choice; it outranks the rule."""
        wm = self._manager(tmp_path)
        wm.set_runtime_slot_overrides({("seg", TARGET_AQUARIUM): "best_seg_lateral.pt"})

        path = wm.get_weight_path_by_method(method="seg", task="aquarium", perspective="top_down")

        assert path == "/w/best_seg_lateral.pt"

    def test_unavailable_perspective_degrades_instead_of_returning_nothing(self, tmp_path: Path):
        """No top-down weight installed must still yield a usable model."""
        wm = self._manager(tmp_path)
        del wm.weights["best_seg_topdown.pt"]

        path = wm.get_weight_path_by_method(method="seg", task="aquarium", perspective="top_down")

        assert path == "/w/best_seg_lateral.pt", "degrade, never lose the detection"


# ---------------------------------------------------------------------------
# v8 (ADR-009 / ADR-012): class roles in the registry, weight sha256 and the
# sha-keyed OpenVINO cache.
# ---------------------------------------------------------------------------

_RAT_ROLES = {"arena": "arena", "experimenter": "context", "rat": "subject"}


def _details(wm: WeightManager, name: str) -> dict:
    details = wm.get_weight_details(name)
    assert details is not None, name
    return details


def _str(value: str | None) -> str:
    assert value is not None
    return value


def _v8_manager(tmp_path: Path) -> WeightManager:
    (tmp_path / "weights").mkdir(parents=True, exist_ok=True)
    return WeightManager(
        settings_obj=load_settings(),
        config_dir=tmp_path,
        weights_dir=tmp_path / "weights",
    )


def _registry_7_2(weight_path: Path) -> dict:
    """A weights_config.json entry exactly as 7.2 wrote it (no class_roles)."""
    return {
        weight_path.name: {
            "path": str(weight_path),
            "is_default": True,
            "type": "det",
            "target": "aquarium",
            "perspective": "top_down",
            "is_default_seg": False,
            "is_default_det": True,
            "is_default_seg_aquarium": False,
            "is_default_seg_zebrafish": False,
            "is_default_det_aquarium": True,
            "is_default_det_zebrafish": False,
            "openvino_path": "",
            "openvino_hash": "",
            "openvino_status": OPENVINO_STATUS_NOT_CONVERTED,
            "last_conversion_error": None,
        }
    }


class TestWeightClassRoles:
    def test_class_roles_survive_save_and_reload(self, tmp_path: Path):
        pt = tmp_path / "weights" / "best_det_topdown_rat_v1.pt"
        wm = _v8_manager(tmp_path)
        pt.write_bytes(b"rat weight")
        wm.discover_weights()

        assert wm.set_weight_class_roles(pt.name, _RAT_ROLES) is True
        reloaded = _v8_manager(tmp_path)

        assert _details(reloaded, pt.name)["class_roles"] == _RAT_ROLES
        on_disk = json.loads((tmp_path / WEIGHTS_CONFIG_FILE).read_text(encoding="utf-8"))
        assert on_disk[pt.name]["class_roles"] == _RAT_ROLES

    def test_invalid_roles_are_refused_and_none_clears(self, tmp_path: Path):
        pt = tmp_path / "weights" / "best_det_topdown_rat_v1.pt"
        wm = _v8_manager(tmp_path)
        pt.write_bytes(b"rat weight")
        wm.discover_weights()

        assert wm.set_weight_class_roles(pt.name, {"rat": "animal"}) is False
        assert "class_roles" not in _details(wm, pt.name)
        assert wm.set_weight_class_roles("missing.pt", _RAT_ROLES) is False

        wm.set_weight_class_roles(pt.name, _RAT_ROLES)
        assert wm.set_weight_class_roles(pt.name, None) is True
        assert "class_roles" not in _details(wm, pt.name)

    def test_registry_from_7_2_without_class_roles_loads_unchanged(self, tmp_path: Path):
        (tmp_path / "weights").mkdir()
        pt = tmp_path / "weights" / "best_det_topdown.pt"
        pt.write_bytes(b"zebrafish weight")
        raw = json.dumps(_registry_7_2(pt), indent=4)
        (tmp_path / WEIGHTS_CONFIG_FILE).write_text(raw, encoding="utf-8")

        wm = _v8_manager(tmp_path)

        assert wm.weights == _registry_7_2(pt)
        assert (tmp_path / WEIGHTS_CONFIG_FILE).read_text(encoding="utf-8") == raw

    def test_discovery_imports_class_roles_from_the_sibling_json(self, tmp_path: Path):
        weights = tmp_path / "weights"
        weights.mkdir()
        (weights / "best_det_topdown_rat_v1.pt").write_bytes(b"rat weight")
        (weights / "best_det_topdown_rat_v1.json").write_text(
            json.dumps(
                {
                    "classes": {"0": "arena", "1": "experimenter", "2": "rat"},
                    "target": "rat",
                    "class_roles": {"Arena": "arena", "Experimenter": "context", "rat": "subject"},
                }
            ),
            encoding="utf-8",
        )

        wm = _v8_manager(tmp_path)
        details = _details(wm, "best_det_topdown_rat_v1.pt")

        assert details["class_roles"] == _RAT_ROLES
        # The registry target is a persistence contract: never "rat".
        assert details["target"] in VALID_TARGETS

    @pytest.mark.parametrize(
        "payload",
        [
            '{"classes": {"0": "rat"}}',
            '{"class_roles": {"rat": "animal"}}',
            '{"class_roles": ["rat"]}',
            "not json",
            '["class_roles"]',
        ],
    )
    def test_sibling_json_without_usable_roles_is_ignored(self, tmp_path: Path, payload: str):
        weights = tmp_path / "weights"
        weights.mkdir()
        (weights / "best_det_topdown_rat_v1.pt").write_bytes(b"rat weight")
        (weights / "best_det_topdown_rat_v1.json").write_text(payload, encoding="utf-8")

        wm = _v8_manager(tmp_path)

        assert "class_roles" not in _details(wm, "best_det_topdown_rat_v1.pt")

    def test_existing_entry_without_roles_picks_up_a_new_sibling(self, tmp_path: Path):
        (tmp_path / "weights").mkdir()
        pt = tmp_path / "weights" / "best_det_topdown.pt"
        pt.write_bytes(b"zebrafish weight")
        (tmp_path / WEIGHTS_CONFIG_FILE).write_text(json.dumps(_registry_7_2(pt)), encoding="utf-8")
        pt.with_suffix(".json").write_text(json.dumps({"class_roles": _RAT_ROLES}), "utf-8")

        wm = _v8_manager(tmp_path)

        assert _details(wm, pt.name)["class_roles"] == _RAT_ROLES

    def test_explicit_registry_roles_are_not_overwritten_by_the_sibling(self, tmp_path: Path):
        (tmp_path / "weights").mkdir()
        pt = tmp_path / "weights" / "best_det_topdown.pt"
        pt.write_bytes(b"zebrafish weight")
        registry = _registry_7_2(pt)
        registry[pt.name]["class_roles"] = {"rat": "subject"}
        (tmp_path / WEIGHTS_CONFIG_FILE).write_text(json.dumps(registry), encoding="utf-8")
        pt.with_suffix(".json").write_text(json.dumps({"class_roles": _RAT_ROLES}), "utf-8")

        wm = _v8_manager(tmp_path)

        assert _details(wm, pt.name)["class_roles"] == {"rat": "subject"}


class TestWeightSha256:
    def test_sha256_matches_the_file_and_tracks_replacement(self, tmp_path: Path):
        import hashlib
        import os

        pt = tmp_path / "weights" / "best_det_topdown.pt"
        wm = _v8_manager(tmp_path)
        pt.write_bytes(b"first")
        wm.discover_weights()

        assert wm.get_weight_sha256(pt.name) == hashlib.sha256(b"first").hexdigest()

        pt.write_bytes(b"second, longer")
        stat = pt.stat()
        os.utime(pt, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))
        assert wm.get_weight_sha256(pt.name) == hashlib.sha256(b"second, longer").hexdigest()

    def test_unknown_or_missing_weight_has_no_sha(self, tmp_path: Path):
        wm = _v8_manager(tmp_path)
        wm.weights["gone.pt"] = {"path": str(tmp_path / "gone.pt")}

        assert wm.get_weight_sha256("gone.pt") == ""
        assert wm.get_weight_sha256("never_registered.pt") == ""
        assert wm.sha256_for_path("") == ""


class TestOpenVINOCacheKeyedBySha:
    def _setup(self, tmp_path: Path) -> tuple[WeightManager, Path, str]:
        import hashlib

        pt = tmp_path / "weights" / "best_det_topdown.pt"
        wm = _v8_manager(tmp_path)
        pt.write_bytes(b"det weight v2")
        wm.discover_weights()
        return wm, pt, hashlib.sha256(b"det weight v2").hexdigest()

    def _fake_export(self, tmp_path: Path, monkeypatch) -> list[dict]:
        """Patch YOLO so an export produces a folder with one .xml."""
        exports = tmp_path / "exports"
        exports.mkdir(exist_ok=True)
        calls: list[dict] = []

        class _FakeYolo:
            def __init__(self, path):
                self.path = path
                self.names = {0: "arena", 1: "rat"}

            def export(self, **kwargs):
                calls.append(kwargs)
                out = exports / f"export_{len(calls)}"
                out.mkdir()
                (out / "model.xml").write_text("<xml/>", encoding="utf-8")
                return str(out)

        monkeypatch.setattr("zebtrack.core.services.weight_manager.ULTRALYTICS_AVAILABLE", True)
        monkeypatch.setattr("zebtrack.core.services.weight_manager.YOLO", _FakeYolo)
        return calls

    def test_cache_dir_name_embeds_the_weight_sha(self, tmp_path: Path, monkeypatch):
        wm, pt, sha = self._setup(tmp_path)
        calls = self._fake_export(tmp_path, monkeypatch)

        path = wm.convert_to_openvino(pt.name)

        expected = tmp_path / OPENVINO_CACHE_DIR / f"best_det_topdown_{sha[:8]}_openvino_model"
        assert Path(_str(path)) == expected
        metadata = json.loads((expected / "metadata.json").read_text(encoding="utf-8"))
        assert metadata["source_sha256"] == sha
        assert len(calls) == 1
        assert wm.openvino_cache_is_current(pt.name) is True

        # Second call reuses the sha-named folder without exporting again.
        assert wm.convert_to_openvino(pt.name) == path
        assert len(calls) == 1

    def test_legacy_dir_with_matching_recorded_sha_is_reused(self, tmp_path: Path, monkeypatch):
        wm, pt, sha = self._setup(tmp_path)
        calls = self._fake_export(tmp_path, monkeypatch)
        legacy = tmp_path / OPENVINO_CACHE_DIR / "best_det_topdown_openvino_model"
        legacy.mkdir(parents=True)
        (legacy / "model.xml").write_text("<xml/>", encoding="utf-8")
        (legacy / "metadata.json").write_text(json.dumps({"source_sha256": sha}), "utf-8")

        path = wm.convert_to_openvino(pt.name)

        assert Path(_str(path)) == legacy
        assert calls == []

    @pytest.mark.parametrize("recorded", [None, "0" * 64])
    def test_legacy_dir_without_or_with_wrong_sha_is_re_exported(
        self, tmp_path: Path, monkeypatch, recorded
    ):
        wm, pt, sha = self._setup(tmp_path)
        calls = self._fake_export(tmp_path, monkeypatch)
        legacy = tmp_path / OPENVINO_CACHE_DIR / "best_det_topdown_openvino_model"
        legacy.mkdir(parents=True)
        (legacy / "model.xml").write_text("<xml/>", encoding="utf-8")
        metadata = {"original_model": pt.name}
        if recorded:
            metadata["source_sha256"] = recorded
        (legacy / "metadata.json").write_text(json.dumps(metadata), "utf-8")

        path = wm.convert_to_openvino(pt.name)

        assert Path(_str(path)).name == f"best_det_topdown_{sha[:8]}_openvino_model"
        assert len(calls) == 1

    def test_registry_pointing_at_a_stale_legacy_export_is_not_current(self, tmp_path: Path):
        wm, pt, _sha = self._setup(tmp_path)
        legacy = tmp_path / OPENVINO_CACHE_DIR / "best_det_topdown_openvino_model"
        legacy.mkdir(parents=True)
        (legacy / "model.xml").write_text("<xml/>", encoding="utf-8")
        details = _details(wm, pt.name)
        details["openvino_path"] = str(legacy)
        details["openvino_status"] = OPENVINO_STATUS_READY

        assert wm.openvino_cache_is_current(pt.name) is False
        assert wm.openvino_cache_is_current("never_registered.pt") is False

    def test_registry_must_point_at_the_current_export_itself(self, tmp_path: Path, monkeypatch):
        wm, pt, _sha = self._setup(tmp_path)
        self._fake_export(tmp_path, monkeypatch)
        wm.convert_to_openvino(pt.name)
        other = tmp_path / OPENVINO_CACHE_DIR / "somewhere_else_openvino_model"
        other.mkdir(parents=True)
        _details(wm, pt.name)["openvino_path"] = str(other)

        assert wm.openvino_cache_is_current(pt.name) is False

    def test_int8_cache_is_keyed_by_sha_too(self, tmp_path: Path, monkeypatch):
        wm, pt, sha = self._setup(tmp_path)
        calls = self._fake_export(tmp_path, monkeypatch)
        legacy = tmp_path / OPENVINO_CACHE_DIR / "best_det_topdown_openvino_int8_model"
        legacy.mkdir(parents=True)
        (legacy / "model.xml").write_text("<xml/>", encoding="utf-8")

        path = wm.convert_to_openvino_int8(pt.name)

        assert Path(_str(path)).name == f"best_det_topdown_{sha[:8]}_openvino_int8_model"
        assert calls == [{"format": "openvino", "int8": True}]
        metadata = json.loads((Path(_str(path)) / "metadata.json").read_text(encoding="utf-8"))
        assert metadata["source_sha256"] == sha
        assert wm.openvino_cache_is_current(pt.name, int8=True) is True

    def test_targets_and_default_flags_keep_their_7_2_names(self):
        assert VALID_TARGETS == ("aquarium", "zebrafish")
        assert _default_flag_key("det", "zebrafish") == "is_default_det_zebrafish"
