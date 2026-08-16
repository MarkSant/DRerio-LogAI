"""
Extended unit tests for BboxAreaGate.
"""

from __future__ import annotations

from types import SimpleNamespace

from zebtrack.core.detection.bbox_area_gate import (
    DEFAULT_RATIO_MAX,
    DEFAULT_WARMUP,
    BboxAreaGate,
)


class TestBboxAreaGateExtended:
    """Test BboxAreaGate rolling median filtering."""

    def test_default_initialization(self):
        gate = BboxAreaGate()
        assert gate.enabled is True
        assert gate.ratio_max == DEFAULT_RATIO_MAX
        assert gate.warmup == DEFAULT_WARMUP
        assert gate.rejections == 0
        assert gate.sample_count == 0

    def test_from_settings_none(self):
        gate = BboxAreaGate.from_settings(None, label="test")
        assert gate.enabled is True
        assert gate.label == "test"
        assert gate.ratio_max == DEFAULT_RATIO_MAX

    def test_from_settings_custom(self):
        settings = SimpleNamespace(
            yolo_model=SimpleNamespace(
                bbox_area_gate_enabled=False,
                bbox_area_median_ratio_max=2.5,
                bbox_area_history_window=20,
                bbox_area_gate_warmup=5,
            )
        )
        gate = BboxAreaGate.from_settings(settings, label="custom")
        assert gate.enabled is False
        assert gate.ratio_max == 2.5
        assert gate.warmup == 5

    def test_warmup_accepts_all_areas(self):
        gate = BboxAreaGate(warmup=5, ratio_max=2.0)
        # Feed 4 samples (below warmup of 5)
        for _ in range(4):
            kept = gate.filter([(0, 0, 10, 10, 0.9, 1, 0)])  # area 100
            assert len(kept) == 1

        # 5th sample (reaches warmup)
        kept = gate.filter([(0, 0, 100, 100, 0.9, 1, 0)])
        assert len(kept) == 1
        assert gate.rejections == 0
        assert gate.sample_count == 5

    def test_rejection_after_warmup(self):
        gate = BboxAreaGate(warmup=5, ratio_max=2.0, window=10)
        # Establish baseline: 5 samples of area 100
        for _ in range(5):
            gate.filter([(0, 0, 10, 10, 0.9, 1, 0)])

        assert gate.sample_count == 5

        # Area 150 (ratio 1.5 < 2.0) -> accepted
        kept = gate.filter([(0, 0, 15, 10, 0.9, 1, 0)])
        assert len(kept) == 1
        assert gate.sample_count == 6

        # Area 300 (ratio 3.0 > 2.0) -> rejected
        rejected = gate.filter([(0, 0, 30, 10, 0.9, 1, 0)])
        assert len(rejected) == 0
        assert gate.rejections == 1
        assert gate.sample_count == 6

    def test_disabled_gate_accepts_everything(self):
        gate = BboxAreaGate(enabled=False, warmup=2, ratio_max=1.5)
        gate.filter([(0, 0, 10, 10, 0.9, 1, 0)])
        gate.filter([(0, 0, 10, 10, 0.9, 1, 0)])
        # Should accept huge box even with low ratio_max
        kept = gate.filter([(0, 0, 1000, 1000, 0.9, 1, 0)])
        assert len(kept) == 1
        assert gate.rejections == 0

    def test_degenerate_box_skipped(self):
        gate = BboxAreaGate(warmup=2)
        # Zero area box
        kept = gate.filter([(10, 10, 10, 10, 0.9, 1, 0)])
        assert len(kept) == 0
        assert gate.sample_count == 0

    def test_reset(self):
        gate = BboxAreaGate(warmup=2)
        gate.filter([(0, 0, 10, 10, 0.9, 1, 0)])
        gate.filter([(0, 0, 10, 10, 0.9, 1, 0)])
        assert gate.sample_count == 2

        gate.reset()
        assert gate.sample_count == 0
        assert gate.rejections == 0
