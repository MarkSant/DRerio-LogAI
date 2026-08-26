"""Precedence and degradation rules for arena auto-detection.

Guards the bug this module was created for: the pre-recorded flow hardcoded
``"det"`` and never read ``aquarium_method`` or ``preserve_real_aquarium_shape``,
so a project configured for segmentation still got a 4-corner rectangle.
"""

from __future__ import annotations

import pytest

from zebtrack.core.services.arena_detection_policy import (
    ArenaDetectionPolicy,
    resolve_arena_detection,
)
from zebtrack.settings import DetectionZonesSettings, ModelSelectionSettings


class _Settings:
    """Minimal stand-in carrying only the two sections the resolver reads."""

    def __init__(self, *, aquarium_method="seg", preserve=False):
        self.model_selection = ModelSelectionSettings(aquarium_method=aquarium_method)
        self.detection_zones = DetectionZonesSettings(preserve_real_aquarium_shape=preserve)


class TestMethodPrecedence:
    def test_explicit_request_beats_project_and_settings(self):
        policy = resolve_arena_detection(
            {"model_selection": {"aquarium_method": "seg"}},
            _Settings(aquarium_method="seg"),
            requested_method="det",
        )
        assert policy.method == "det"

    def test_project_beats_settings(self):
        policy = resolve_arena_detection(
            {"model_selection": {"aquarium_method": "det"}},
            _Settings(aquarium_method="seg"),
        )
        assert policy.method == "det"

    def test_settings_used_when_project_is_silent(self):
        policy = resolve_arena_detection({}, _Settings(aquarium_method="seg"))
        assert policy.method == "seg"

    def test_project_dict_without_the_key_still_consults_settings(self):
        """A ``model_selection`` dict WITHOUT ``aquarium_method`` is not a choice.

        Branching on the presence of the enclosing dict (rather than the key)
        is the exact mistake that pinned one flow to "det" while the other
        honoured the settings.
        """
        policy = resolve_arena_detection(
            {"model_selection": {"animal_method": "det"}},
            _Settings(aquarium_method="seg"),
        )
        assert policy.method == "seg"

    def test_falls_back_to_det_with_nothing_configured(self):
        assert resolve_arena_detection(None, None).method == "det"

    @pytest.mark.parametrize("garbage", ["segmentation", "", 7, "DET "])
    def test_invalid_project_method_degrades_to_settings(self, garbage):
        policy = resolve_arena_detection(
            {"model_selection": {"aquarium_method": garbage}},
            _Settings(aquarium_method="seg"),
        )
        # "DET " normalises to a valid method; anything else falls through.
        expected = "det" if str(garbage).strip().lower() == "det" else "seg"
        assert policy.method == expected

    def test_method_is_case_insensitive(self):
        policy = resolve_arena_detection(
            {"model_selection": {"aquarium_method": "SEG"}}, _Settings(aquarium_method="det")
        )
        assert policy.method == "seg"


class TestPreserveRealShapePrecedence:
    def test_project_beats_settings(self):
        policy = resolve_arena_detection(
            {"preserve_real_aquarium_shape": False}, _Settings(preserve=True)
        )
        assert policy.preserve_real_shape is False

    def test_settings_used_when_project_is_silent(self):
        assert resolve_arena_detection({}, _Settings(preserve=True)).preserve_real_shape is True

    def test_defaults_to_false(self):
        assert resolve_arena_detection(None, None).preserve_real_shape is False

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [("true", True), ("False", False), (1, True), (0, False), ("yes", True), ("off", False)],
    )
    def test_hand_edited_json_shapes_are_accepted(self, raw, expected):
        policy = resolve_arena_detection({"preserve_real_aquarium_shape": raw}, _Settings())
        assert policy.preserve_real_shape is expected

    @pytest.mark.parametrize("settings_value", [True, False])
    def test_garbage_degrades_to_settings_instead_of_raising(self, settings_value):
        """A corrupt flag must not turn "detect the arena" into a traceback.

        Both settings values are exercised: degrading has to mean "fall through
        to the next level", not "assume True". Assuming True would keep the raw
        mask outline on a project that deliberately asked for a rectangle.
        """
        policy = resolve_arena_detection(
            {"preserve_real_aquarium_shape": "maybe"}, _Settings(preserve=settings_value)
        )
        assert policy.preserve_real_shape is settings_value

    def test_garbage_with_no_settings_defaults_to_false(self):
        policy = resolve_arena_detection({"preserve_real_aquarium_shape": object()}, None)
        assert policy.preserve_real_shape is False


class TestIndependenceAndUsesMasks:
    def test_keys_resolve_independently(self):
        """Project pins the family; the shape still comes from the settings."""
        policy = resolve_arena_detection(
            {"model_selection": {"aquarium_method": "seg"}},
            _Settings(aquarium_method="det", preserve=True),
        )
        assert policy == ArenaDetectionPolicy(method="seg", preserve_real_shape=True)

    def test_uses_masks_requires_both(self):
        assert resolve_arena_detection(
            {"model_selection": {"aquarium_method": "seg"}, "preserve_real_aquarium_shape": True},
            None,
        ).uses_masks
        # A box model has no mask to preserve, so the flag alone is inert.
        assert not resolve_arena_detection(
            {"model_selection": {"aquarium_method": "det"}, "preserve_real_aquarium_shape": True},
            None,
        ).uses_masks
        assert not resolve_arena_detection(
            {"model_selection": {"aquarium_method": "seg"}, "preserve_real_aquarium_shape": False},
            None,
        ).uses_masks

    def test_policy_is_immutable(self):
        policy = resolve_arena_detection({}, None)
        with pytest.raises(AttributeError):
            policy.method = "seg"  # type: ignore[misc]
