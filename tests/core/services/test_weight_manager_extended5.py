"""Extended unit tests for core/services/weight_manager.py."""

from __future__ import annotations

from pathlib import Path

from zebtrack.core.services.weight_manager import WeightManager


class TestWeightManagerExtended5:
    """Test WeightManager weights directory resolution and slot overrides."""

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
