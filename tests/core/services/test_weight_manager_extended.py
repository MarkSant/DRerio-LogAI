"""
Extended unit tests for WeightManager in core/services/weight_manager.py.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from zebtrack.core.services.weight_manager import (
    OPENVINO_STATUS_NOT_CONVERTED,
    TARGET_AQUARIUM,
    TARGET_ZEBRAFISH,
    OpenVINOExportError,
    WeightManager,
    _default_flag_key,
    _default_target_for_type,
)
from zebtrack.settings import load_settings


class TestWeightManagerExtended:
    """Test extended WeightManager operations, slots, taxonomy, and migrations."""

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
