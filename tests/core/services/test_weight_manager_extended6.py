"""Extended unit tests for core/services/weight_manager.py (Part 6)."""

from __future__ import annotations

from pathlib import Path

from zebtrack.core.services.weight_manager import WeightManager


class TestWeightManagerExtended6:
    """Test WeightManager filename resolution and path anchoring."""

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
