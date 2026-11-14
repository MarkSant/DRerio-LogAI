"""Box colour and label by class role (``ui/components/canvas/overlay_roles.py``).

The legacy rows pin the 7.2 behaviour byte for byte: without an explicit role
map nothing about a zebrafish overlay may move.
"""

from __future__ import annotations

from typing import Any

import pytest

from zebtrack.ui.components.canvas.overlay_roles import (
    CANVAS_ROLE_COLORS,
    FRAME_ROLE_COLORS,
    frame_style,
    role_of_class,
    zone_canvas_style,
)

BARNES_ROLES = {0: "arena", 1: "context", 2: "subject", 3: "context"}
BARNES_NAMES = {0: "arena", 1: "experimenter", 2: "rat", 3: "start_box"}


class TestRoleOfClass:
    def test_no_map_means_legacy(self) -> None:
        assert role_of_class(0, None) is None
        assert role_of_class(0, {}) is None

    def test_listed_and_unlisted_classes(self) -> None:
        assert role_of_class(2, BARNES_ROLES) == "subject"
        assert role_of_class(2.0, BARNES_ROLES) == "subject"
        assert role_of_class(9, BARNES_ROLES) == "ignored"
        assert role_of_class("x", BARNES_ROLES) == "ignored"


class TestZoneCanvasLegacy:
    @pytest.mark.parametrize(
        ("class_id", "track_id", "single", "expected"),
        [
            (0, 4, False, ("yellow", "ID: 4")),
            (1, 4, False, ("cyan", "ID: 4")),
            (1, None, False, ("cyan", "Det")),
            (0, 4, True, ("yellow", "Target")),
            (1, 4, True, ("magenta", "Target")),
        ],
    )
    def test_7_2_colours_and_labels(self, class_id, track_id, single, expected) -> None:
        assert zone_canvas_style(class_id, track_id, is_single_subject=single) == expected


class TestZoneCanvasByRole:
    def test_subject_keeps_the_mode_colour_even_at_id_zero(self) -> None:
        roles = {0: "subject", 1: "arena"}
        assert zone_canvas_style(0, 7, is_single_subject=False, class_roles=roles) == (
            "cyan",
            "ID: 7",
        )
        assert zone_canvas_style(0, 7, is_single_subject=True, class_roles=roles) == (
            "magenta",
            "Target",
        )

    def test_arena_context_and_ignored(self) -> None:
        kwargs: dict[str, Any] = {"is_single_subject": False, "class_roles": BARNES_ROLES}
        assert zone_canvas_style(0, None, **kwargs) == (CANVAS_ROLE_COLORS["arena"], "Arena")
        assert zone_canvas_style(1, None, **kwargs) == (CANVAS_ROLE_COLORS["context"], "Context")
        assert zone_canvas_style(9, None, **kwargs) == (CANVAS_ROLE_COLORS["ignored"], "Ignored")

    def test_context_is_labelled_by_class_name(self) -> None:
        style = zone_canvas_style(
            1, None, is_single_subject=False, class_roles=BARNES_ROLES, class_names=BARNES_NAMES
        )
        assert style == ("orange", "experimenter")

    def test_colours_are_distinct(self) -> None:
        assert len(set(CANVAS_ROLE_COLORS.values()) | {"cyan", "magenta"}) == 5


class TestFrameStyle:
    def test_legacy(self) -> None:
        assert frame_style(0, 3) == ((0, 255, 255), "ID 3")
        assert frame_style(1, None) == ((255, 0, 255), "Object")

    def test_by_role(self) -> None:
        assert frame_style(2, 5, class_roles=BARNES_ROLES) == (FRAME_ROLE_COLORS["subject"], "ID 5")
        assert frame_style(0, None, class_roles=BARNES_ROLES) == (
            FRAME_ROLE_COLORS["arena"],
            "Arena",
        )
        assert frame_style(3, None, class_roles=BARNES_ROLES, class_names=BARNES_NAMES) == (
            (0, 165, 255),
            "start_box",
        )
        assert frame_style(3, None, class_roles=BARNES_ROLES, class_names={3: ""}) == (
            (0, 165, 255),
            "Context",
        )
        assert frame_style(8, None, class_roles=BARNES_ROLES) == ((160, 160, 160), "Ignored")

    def test_subject_at_id_zero_is_not_painted_as_the_arena(self) -> None:
        assert frame_style(0, 1, class_roles={0: "subject"})[0] == (255, 0, 255)


class TestStubSafety:
    def test_a_non_mapping_is_no_map(self) -> None:
        from unittest.mock import MagicMock

        assert role_of_class(0, MagicMock()) is None  # type: ignore[arg-type]
        assert frame_style(0, 1, class_roles=MagicMock(), class_names=MagicMock()) == (  # type: ignore[arg-type]
            (0, 255, 255),
            "ID 1",
        )
        assert zone_canvas_style(
            1,
            None,
            is_single_subject=False,
            class_roles={1: "context"},
            class_names=MagicMock(),  # type: ignore[arg-type]
        ) == ("orange", "Context")
