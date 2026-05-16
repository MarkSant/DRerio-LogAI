"""Tests for PreviewPolygonDialog — Etapa 3 (vertex drag + manual badge).

Covers the interactive editing flow added on top of the auto-detected
polygon preview:

* Dragging any vertex marks the polygon as ``self._edited = True``, flips
  the badge to "Editado manualmente" and tags ``result["source"] = "manual"``.
* A successful retry (callback returned a new polygon) resets the flag and
  the badge back to "Auto-detectado".
* When the user approves without any drag, ``result["source"] == "auto"``.

Notes:
    The dialog is constructed via ``__new__`` so we never touch Tkinter; all
    Tk variables / canvas / dialog handles are replaced by ``MagicMock``s.
    The methods exercised here are pure logic — they only read/write
    ``self.polygon``, ``self._edited`` and call mocked helpers.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

import numpy as np

from zebtrack.ui.dialogs.preview_polygon_dialog import (
    _BADGE_AUTO_TEXT,
    _BADGE_MANUAL_TEXT,
    PreviewPolygonDialog,
)

# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _make_dialog(
    polygon: list[list[float]] | None = None,
    *,
    scale: float = 1.0,
    edited: bool = False,
) -> PreviewPolygonDialog:
    """Build a PreviewPolygonDialog bypassing Tk initialization."""
    dialog = cast(Any, PreviewPolygonDialog.__new__(PreviewPolygonDialog))
    dialog.frame = np.zeros((480, 640, 3), dtype=np.uint8)
    dialog.polygon = (
        polygon
        if polygon is not None
        else [
            [100.0, 100.0],
            [200.0, 100.0],
            [200.0, 200.0],
            [100.0, 200.0],
        ]
    )
    dialog.result = None
    dialog._edited = edited
    dialog._dragging_vertex_idx = None
    dialog._scale = scale
    dialog._vertex_pick_radius_px = 14
    dialog._retried_frame = None
    dialog._on_retry = None
    dialog._retry_button = None

    # Tk-flavored attributes replaced with mocks (no Tk root in tests).
    dialog._conf_var = MagicMock()
    dialog._conf_var.get.return_value = 0.07
    dialog._conf_text_var = MagicMock()
    dialog._status_var = MagicMock()
    dialog._badge_var = MagicMock()
    dialog._badge_label = MagicMock()
    dialog._canvas = MagicMock()
    dialog.photo = None
    dialog.dialog = MagicMock()

    # `_refresh_canvas` rebuilds a PhotoImage which needs a Tk root; mock it.
    dialog._refresh_canvas = MagicMock()  # type: ignore[method-assign]
    return cast(PreviewPolygonDialog, dialog)


def _event(x: float, y: float) -> SimpleNamespace:
    return SimpleNamespace(x=x, y=y)


# ---------------------------------------------------------------------------
# Helper-level tests
# ---------------------------------------------------------------------------


def test_find_nearest_vertex_returns_idx_within_pick_radius():
    dialog = _make_dialog()

    # Vertex 0 is at (100, 100); click at (102, 98) → 2.83 px away (< 14).
    assert dialog._find_nearest_vertex(102, 98) == 0


def test_find_nearest_vertex_returns_none_outside_radius():
    dialog = _make_dialog()

    # No vertex within 14 px of (50, 50).
    assert dialog._find_nearest_vertex(50, 50) is None


def test_canvas_to_image_coords_inverts_scale():
    dialog = _make_dialog(scale=0.5)

    # Canvas coords are at half the native size; clicking (60, 80) on canvas
    # corresponds to (120, 160) on the native frame.
    assert dialog._canvas_to_image_coords(60, 80) == (120.0, 160.0)


def test_find_nearest_vertex_respects_scale():
    """When the preview is downscaled the displayed vertex moves with scale."""
    dialog = _make_dialog(scale=0.5)
    # Native vertex (200, 100) renders at canvas (100, 50).
    assert dialog._find_nearest_vertex(100, 50) == 1


# ---------------------------------------------------------------------------
# Drag flow
# ---------------------------------------------------------------------------


def test_polygon_drag_marks_as_manual_and_updates_badge():
    dialog = _make_dialog()

    # Pick vertex 0 at (100, 100).
    dialog._on_canvas_press(_event(101, 100))
    assert dialog._dragging_vertex_idx == 0

    # Drag to a new location (canvas coords; scale=1 so same as native coords).
    dialog._on_canvas_drag(_event(150, 130))

    assert dialog._edited is True
    assert dialog.polygon[0] == [150.0, 130.0]

    # Badge variable updated to manual text.
    cast(MagicMock, dialog._badge_var).set.assert_called_with(_BADGE_MANUAL_TEXT)
    # Badge label background reconfigured (color flipped to orange).
    cast(MagicMock, dialog._badge_label).config.assert_called()
    config_call_kwargs = cast(MagicMock, dialog._badge_label).config.call_args.kwargs
    assert "bg" in config_call_kwargs

    # Re-render of preview was triggered.
    cast(MagicMock, dialog._refresh_canvas).assert_called()

    # Release drops the picked vertex.
    dialog._on_canvas_release(_event(150, 130))
    assert dialog._dragging_vertex_idx is None

    # Approve carries the updated polygon and a manual source.
    dialog._on_approve()
    assert dialog.result is not None
    assert dialog.result["approved"] is True
    assert dialog.result["source"] == "manual"
    assert dialog.result["edited"] is True
    assert dialog.result["polygon"][0] == [150.0, 130.0]


def test_drag_marks_edited_only_once_for_repeated_motion():
    dialog = _make_dialog()
    dialog._on_canvas_press(_event(100, 100))

    dialog._on_canvas_drag(_event(110, 110))
    dialog._on_canvas_drag(_event(120, 120))
    dialog._on_canvas_drag(_event(130, 130))

    assert dialog._edited is True
    # Polygon reflects the latest drag position.
    assert dialog.polygon[0] == [130.0, 130.0]
    # The badge text was set to manual at least once; subsequent drags
    # shouldn't flip-flop the badge state.
    badge_set_mock = cast(MagicMock, dialog._badge_var).set
    manual_set_calls = [c for c in badge_set_mock.call_args_list if c.args == (_BADGE_MANUAL_TEXT,)]
    assert len(manual_set_calls) == 1


def test_press_outside_radius_does_not_pick_vertex():
    dialog = _make_dialog()
    dialog._on_canvas_press(_event(400, 400))
    assert dialog._dragging_vertex_idx is None

    # Drag after a miss is a no-op.
    dialog._on_canvas_drag(_event(401, 401))
    assert dialog._edited is False


# ---------------------------------------------------------------------------
# Approve / reject result payload
# ---------------------------------------------------------------------------


def test_no_edit_returns_source_auto():
    dialog = _make_dialog()
    dialog._on_approve()

    assert dialog.result is not None
    assert dialog.result["approved"] is True
    assert dialog.result["source"] == "auto"
    assert dialog.result["edited"] is False
    assert dialog.result["polygon"] == [
        [100.0, 100.0],
        [200.0, 100.0],
        [200.0, 200.0],
        [100.0, 200.0],
    ]


def test_reject_returns_manual_source_for_downstream_routing():
    dialog = _make_dialog()
    dialog._on_reject()

    assert dialog.result is not None
    assert dialog.result["approved"] is False
    assert dialog.result["polygon"] is None
    # Rejection always implies the user is about to draw manually.
    assert dialog.result["source"] == "manual"


# ---------------------------------------------------------------------------
# Retry flow
# ---------------------------------------------------------------------------


def test_retry_resets_manual_flag_and_badge():
    """After a manual edit, a successful retry must restore auto provenance."""
    dialog = _make_dialog()

    # Simulate a manual drag first.
    dialog._on_canvas_press(_event(100, 100))
    dialog._on_canvas_drag(_event(150, 150))
    assert dialog._edited is True

    new_polygon = [[10.0, 10.0], [600.0, 10.0], [600.0, 470.0], [10.0, 470.0]]
    new_frame = np.full((480, 640, 3), 17, dtype=np.uint8)
    dialog._on_retry = MagicMock(return_value=(new_frame, new_polygon))

    dialog._on_retry_click()

    assert dialog._edited is False
    assert dialog.polygon == new_polygon
    assert dialog._retried_frame is new_frame

    # Badge flipped back to auto (this is the latest set call).
    cast(MagicMock, dialog._badge_var).set.assert_called_with(_BADGE_AUTO_TEXT)

    # Approving now reports source=auto, despite the earlier drag.
    dialog._on_approve()
    assert dialog.result is not None
    assert dialog.result["source"] == "auto"
    assert dialog.result["edited"] is False
    assert dialog.result["frame"] is new_frame


def test_retry_failure_keeps_existing_polygon_and_state():
    dialog = _make_dialog()
    dialog._on_retry = MagicMock(return_value=None)

    original_polygon = list(dialog.polygon)
    dialog._on_retry_click()

    # No new polygon → keep current.
    assert dialog.polygon == original_polygon
    # Status was updated to indicate the failure path.
    cast(MagicMock, dialog._status_var).set.assert_called()
