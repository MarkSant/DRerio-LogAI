"""
Extended unit tests for WeightManager.

Tests perspective matching, legacy type defaults, filename resolution,
runtime slot overrides, and weight addition validation.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

from zebtrack.core.services.weight_manager import WeightManager


class TestWeightManagerExtended:
    """Test extended WeightManager operations."""

    def _create_weight_manager(self, tmp_path: Path) -> WeightManager:
        settings = SimpleNamespace(
            weights=SimpleNamespace(source_dir=str(tmp_path / "weights")),
            model=SimpleNamespace(weights_dir=str(tmp_path / "weights")),
            hardware=SimpleNamespace(openvino=SimpleNamespace(device="AUTO")),
        )
        (tmp_path / "weights").mkdir(parents=True, exist_ok=True)
        return WeightManager(settings_obj=cast(Any, settings))

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
