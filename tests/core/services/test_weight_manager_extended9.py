"""Extended unit tests for core/services/weight_manager.py (Part 9)."""

from __future__ import annotations

from zebtrack.core.services.weight_manager import WeightManager


class TestWeightManagerExtended9:
    """Test WeightManager runtime overrides dictionary mapping."""

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
