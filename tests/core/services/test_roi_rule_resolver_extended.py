"""
Extended unit tests for RoiRuleConfig and roi_rule_resolver.
"""

from __future__ import annotations

import math
from types import SimpleNamespace
from typing import Any, cast

from zebtrack.core.services.roi_rule_resolver import (
    RoiRuleConfig,
    apply_roi_rule_to_settings,
)


class TestRoiRuleConfigExtended:
    """Test RoiRuleConfig properties, serialization, and settings application."""

    def test_config_properties_and_aliases(self):
        cfg = RoiRuleConfig(
            rule="bbox_intersects",
            buffer_radius_value=2.5,
            min_bbox_overlap_ratio=0.0,
            min_seg_overlap_ratio=0.4,
            bbox_overlap_basis="roi",
            flutter_enter_frames=4,
            flutter_exit_frames=5,
            min_visit_s=0.5,
            min_gap_s=0.1,
            max_gap_s=2.0,
        )

        assert cfg.uses_bbox is True
        assert cfg.uses_buffer is False
        assert cfg.overlap_any is True

        assert cfg.roi_inclusion_rule == "bbox_intersects"
        assert cfg.roi_buffer_radius_value == 2.5
        assert cfg.roi_min_bbox_overlap_ratio == 0.0
        assert cfg.roi_min_seg_overlap_ratio == 0.4
        assert cfg.roi_bbox_overlap_basis == "roi"
        assert cfg.roi_flutter_enter_frames == 4
        assert cfg.roi_flutter_exit_frames == 5
        assert cfg.roi_min_visit_s == 0.5
        assert cfg.roi_min_gap_s == 0.1
        assert cfg.roi_max_gap_s == 2.0

        d = cfg.to_roi_settings()
        assert d["roi_inclusion_rule"] == "bbox_intersects"
        assert d["roi_buffer_radius_value"] == 2.5
        assert d["roi_min_bbox_overlap_ratio"] == 0.0
        assert d["roi_min_seg_overlap_ratio"] == 0.4
        assert d["roi_bbox_overlap_basis"] == "roi"
        assert d["roi_flutter_enter_frames"] == 4
        assert d["roi_flutter_exit_frames"] == 5
        assert d["roi_min_visit_s"] == 0.5
        assert d["roi_min_gap_s"] == 0.1
        assert d["roi_max_gap_s"] == 2.0

    def test_apply_roi_rule_to_settings(self):
        cfg = RoiRuleConfig(
            rule="centroid_in_on_buffered_roi",
            buffer_radius_value=3.0,
            min_bbox_overlap_ratio=0.2,
            min_seg_overlap_ratio=0.5,
            bbox_overlap_basis="bbox",
            flutter_enter_frames=1,
            flutter_exit_frames=2,
            min_visit_s=0.3,
            min_gap_s=0.0,
            max_gap_s=math.inf,
        )

        settings = SimpleNamespace()
        apply_roi_rule_to_settings(cast(Any, settings), cfg)

        assert settings.roi_inclusion_rule == "centroid_in_on_buffered_roi"
        assert settings.roi_buffer_radius_value == 3.0
        assert settings.roi_min_bbox_overlap_ratio == 0.2
        assert settings.roi_min_seg_overlap_ratio == 0.5
        assert settings.roi_bbox_overlap_basis == "bbox"
        assert settings.roi_flutter_enter_frames == 1
        assert settings.roi_flutter_exit_frames == 2
        assert settings.roi_min_visit_s == 0.3
        assert settings.roi_min_gap_s == 0.0
        assert settings.roi_max_gap_s == math.inf
