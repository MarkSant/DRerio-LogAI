"""Extended unit tests for core/services/weight_manager.py (Part 8)."""

from __future__ import annotations

from pathlib import Path

from zebtrack.core.services.weight_manager import WeightManager


class TestWeightManagerExtended8:
    """Test WeightManager path relocation and initialization guards."""

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
