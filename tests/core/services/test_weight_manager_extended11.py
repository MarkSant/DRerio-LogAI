"""Extended unit tests for core/services/weight_manager.py (Part 11)."""

from __future__ import annotations

from zebtrack.core.services.weight_manager import (
    TARGET_AQUARIUM,
    TARGET_ZEBRAFISH,
    VALID_METHODS,
    VALID_TARGETS,
    WeightManager,
)


class TestWeightManagerExtended11:
    """Test WeightManager constants and target taxonomy definitions."""

    def test_target_taxonomy_constants(self):
        assert TARGET_AQUARIUM == "aquarium"
        assert TARGET_ZEBRAFISH == "zebrafish"
        assert VALID_TARGETS == ("aquarium", "zebrafish")
        assert VALID_METHODS == ("seg", "det")

    def test_weight_manager_init(self):
        mgr = WeightManager(settings_obj=None)
        assert isinstance(mgr, WeightManager)
