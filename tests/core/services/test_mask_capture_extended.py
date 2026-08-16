"""
Extended unit tests for mask_capture.
"""

from __future__ import annotations

from types import SimpleNamespace

from zebtrack.core.services.mask_capture import should_capture_masks


class TestMaskCaptureExtended:
    """Test should_capture_masks decision matrix."""

    def test_settings_none_returns_false(self):
        assert should_capture_masks(None) is False

    def test_persist_masks_disabled_returns_false(self):
        settings = SimpleNamespace(
            recorder=SimpleNamespace(persist_masks=False),
            model_selection=SimpleNamespace(animal_method="seg"),
            roi_inclusion_rule="seg_overlap",
        )
        assert should_capture_masks(settings) is False

    def test_animal_method_det_returns_false(self):
        settings = SimpleNamespace(
            recorder=SimpleNamespace(persist_masks=True),
            model_selection=SimpleNamespace(animal_method="det"),
            roi_inclusion_rule="seg_overlap",
        )
        assert should_capture_masks(settings) is False

    def test_rule_not_seg_overlap_returns_false(self):
        settings = SimpleNamespace(
            recorder=SimpleNamespace(persist_masks=True),
            model_selection=SimpleNamespace(animal_method="seg"),
            roi_inclusion_rule="bbox_intersects",
        )
        assert should_capture_masks(settings) is False

    def test_all_conditions_met_returns_true(self):
        settings = SimpleNamespace(
            recorder=SimpleNamespace(persist_masks=True),
            model_selection=SimpleNamespace(animal_method="seg"),
            roi_inclusion_rule="seg_overlap",
            roi_buffer_radius_value=0.5,
            roi_min_bbox_overlap_ratio=0.1,
            roi_min_seg_overlap_ratio=0.3,
            roi_bbox_overlap_basis="bbox",
        )
        assert should_capture_masks(settings) is True

    def test_project_data_override_enables_mask_capture(self):
        settings = SimpleNamespace(
            recorder=SimpleNamespace(persist_masks=True),
            model_selection=SimpleNamespace(animal_method="seg"),
            roi_inclusion_rule="bbox_intersects",
            roi_buffer_radius_value=0.5,
            roi_min_bbox_overlap_ratio=0.1,
            roi_min_seg_overlap_ratio=0.3,
            roi_bbox_overlap_basis="bbox",
        )
        # Project overrides rule to seg_overlap
        project_data = {"roi_settings": {"roi_inclusion_rule": "seg_overlap"}}
        assert should_capture_masks(settings, project_data) is True
