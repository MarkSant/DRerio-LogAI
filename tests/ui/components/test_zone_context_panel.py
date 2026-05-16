"""Tests for ``ZoneContextPanel`` (Etapa 4).

The panel is a thin Tk wrapper; the unit tests exercise the *update* logic
plus the event-bus subscription path without instantiating any real widgets.
Tk handles are replaced with ``MagicMock``s following the pattern from
``tests/ui/dialogs/test_subject_selection_dialog.py``.
"""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock

from zebtrack.ui.components.zone_context_panel import (
    _BADGE_STYLES,
    ZoneContextPanel,
    _badge_visuals,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bare_panel(
    *,
    project_manager: Any | None = None,
    weight_manager: Any | None = None,
    event_bus: Any | None = None,
    root: Any | None = None,
) -> ZoneContextPanel:
    """Build a ZoneContextPanel with Tk widget slots pre-populated by Mocks.

    Bypasses ``build()`` so tests don't touch tkinter, while still letting
    ``update()`` and the event handlers exercise the production code paths
    that touch ``self._source_label`` / ``_model_label`` / ``_badge_label``.
    """
    panel = cast(Any, ZoneContextPanel.__new__(ZoneContextPanel))
    panel._event_bus = event_bus
    panel._project_manager = project_manager
    panel._weight_manager = weight_manager
    panel._root = root
    panel._active_source = "—"
    panel._model_caption = "—"
    panel._polygon_source = None
    panel.frame = MagicMock()
    panel._source_label = MagicMock()
    panel._model_label = MagicMock()
    panel._badge_label = MagicMock()
    panel._subscribed = False
    return cast(ZoneContextPanel, panel)


# ---------------------------------------------------------------------------
# Badge rendering
# ---------------------------------------------------------------------------


def test_badge_visuals_for_auto_returns_green_style():
    text, fg, bg = _badge_visuals("auto")
    assert text == _BADGE_STYLES["auto"][0]
    assert fg == "white"
    assert bg == "#2e7d32"


def test_badge_visuals_for_manual_returns_orange_style():
    text, fg, bg = _badge_visuals("manual")
    assert text == _BADGE_STYLES["manual"][0]
    assert bg == "#ef6c00"


def test_badge_visuals_for_none_returns_gray_style():
    text, fg, bg = _badge_visuals(None)
    assert text == _BADGE_STYLES["none"][0]
    assert bg == "#757575"


def test_badge_visuals_for_unknown_source_falls_back_to_none():
    text, _, bg = _badge_visuals("garbage")
    assert text == _BADGE_STYLES["none"][0]
    assert bg == "#757575"


# ---------------------------------------------------------------------------
# update() rendering
# ---------------------------------------------------------------------------


def test_update_auto_polygon_source_writes_green_badge():
    panel = _bare_panel()
    panel.update(polygon_source="auto")
    badge = cast(MagicMock, panel._badge_label)
    badge.config.assert_called_once()
    kwargs = badge.config.call_args.kwargs
    assert kwargs["text"] == _BADGE_STYLES["auto"][0]
    assert kwargs["background"] == "#2e7d32"


def test_update_manual_polygon_source_writes_orange_badge():
    panel = _bare_panel()
    panel.update(polygon_source="manual")
    kwargs = cast(MagicMock, panel._badge_label).config.call_args.kwargs
    assert kwargs["text"] == _BADGE_STYLES["manual"][0]
    assert kwargs["background"] == "#ef6c00"


def test_update_none_polygon_source_writes_gray_badge():
    panel = _bare_panel()
    panel._polygon_source = "auto"  # start from a non-empty state
    panel.update(polygon_source=None)
    kwargs = cast(MagicMock, panel._badge_label).config.call_args.kwargs
    assert kwargs["text"] == _BADGE_STYLES["none"][0]
    assert kwargs["background"] == "#757575"


def test_update_sentinel_default_leaves_badge_untouched():
    """Calling update() without ``polygon_source=`` must not rewrite the badge."""
    panel = _bare_panel()
    panel.update(active_source="foo.mp4")
    cast(MagicMock, panel._badge_label).config.assert_not_called()


def test_update_active_source_writes_formatted_label():
    panel = _bare_panel()
    panel.update(active_source="trial_42.mp4")
    cast(MagicMock, panel._source_label).config.assert_called_once_with(
        text="Fonte ativa: trial_42.mp4"
    )


def test_update_model_caption_writes_formatted_label():
    panel = _bare_panel()
    panel.update(model_caption="aquarium_seg.pt · método seg")
    cast(MagicMock, panel._model_label).config.assert_called_once_with(
        text="Modelo do aquário: aquarium_seg.pt · método seg"
    )


# ---------------------------------------------------------------------------
# Event handlers
# ---------------------------------------------------------------------------


def test_polygon_source_event_dispatches_via_root_after():
    """Handler must marshal the badge update onto the Tk main thread."""
    captured: list[Any] = []
    root = MagicMock()
    root.after.side_effect = lambda _delay, fn: captured.append(fn)

    panel = _bare_panel(root=root)
    payload = MagicMock(source="auto")

    panel._on_polygon_source_event(payload)

    root.after.assert_called_once()
    delay = root.after.call_args.args[0]
    assert delay == 0
    # Execute the marshaled callback and verify the badge mutated.
    assert captured, "callback should have been queued onto root.after"
    captured[0]()
    kwargs = cast(MagicMock, panel._badge_label).config.call_args.kwargs
    assert kwargs["text"] == _BADGE_STYLES["auto"][0]


def test_video_frame_event_updates_active_source_with_basename():
    captured: list[Any] = []
    root = MagicMock()
    root.after.side_effect = lambda _delay, fn: captured.append(fn)

    panel = _bare_panel(root=root)
    payload = MagicMock(video_path="/tmp/experiment_07/session_a.mp4")

    panel._on_video_frame_event(payload)

    assert captured
    captured[0]()
    cast(MagicMock, panel._source_label).config.assert_called_once_with(
        text="Fonte ativa: session_a.mp4"
    )


def test_video_frame_event_for_live_reference_frame_shows_camera_label():
    """The reference frame written during live calibration must not be shown
    as if the user opened a file — it's an internal artefact of the live flow."""
    project_manager = MagicMock()
    project_manager.get_project_type.return_value = "live"
    project_manager.project_data = {"camera_index": 2}

    captured: list[Any] = []
    root = MagicMock()
    root.after.side_effect = lambda _delay, fn: captured.append(fn)

    panel = _bare_panel(project_manager=project_manager, root=root)
    panel._on_video_frame_event(MagicMock(video_path="/foo/live_camera_reference_frame.png"))

    captured[0]()
    cast(MagicMock, panel._source_label).config.assert_called_once_with(
        text="Fonte ativa: Câmera ao vivo (idx 2)"
    )


def test_project_opened_event_triggers_refresh_from_project():
    project_manager = MagicMock()
    project_manager.get_project_type.return_value = "live"
    project_manager.project_data = {"camera_index": 0}
    project_manager.get_zone_data.return_value = None
    weight_manager = MagicMock()
    weight_manager.get_weight_path_by_method.return_value = "/models/aquarium.pt"

    captured: list[Any] = []
    root = MagicMock()
    root.after.side_effect = lambda _delay, fn: captured.append(fn)

    panel = _bare_panel(
        project_manager=project_manager,
        weight_manager=weight_manager,
        root=root,
    )
    panel._on_project_opened(MagicMock(project_path="/proj"))

    captured[0]()
    cast(MagicMock, panel._source_label).config.assert_called_with(
        text="Fonte ativa: Câmera ao vivo (idx 0)"
    )
    cast(MagicMock, panel._model_label).config.assert_called_with(
        text="Modelo do aquário: aquarium.pt · método det"
    )


# ---------------------------------------------------------------------------
# refresh_from_project()
# ---------------------------------------------------------------------------


def test_refresh_from_project_pre_recorded_shows_placeholder_source():
    """For non-live projects with no active video, source falls back to '—'."""
    project_manager = MagicMock()
    project_manager.get_project_type.return_value = "pre_recorded"
    project_manager.project_data = {}
    project_manager.get_zone_data.return_value = None

    panel = _bare_panel(project_manager=project_manager)
    panel.refresh_from_project()

    cast(MagicMock, panel._source_label).config.assert_called_with(text="Fonte ativa: —")


def test_refresh_from_project_seeds_badge_from_existing_zone_metadata():
    """If the project already has zones with ``detection_method``, the badge
    must reflect that provenance even before any live calibration runs."""
    project_manager = MagicMock()
    project_manager.get_project_type.return_value = "pre_recorded"
    project_manager.project_data = {}
    zone_data = MagicMock()
    zone_data.polygon = [[0, 0], [1, 0], [1, 1], [0, 1]]
    zone_data.metadata = {"detection_method": "auto"}
    project_manager.get_zone_data.return_value = zone_data

    panel = _bare_panel(project_manager=project_manager)
    panel.refresh_from_project()

    kwargs = cast(MagicMock, panel._badge_label).config.call_args.kwargs
    assert kwargs["text"] == _BADGE_STYLES["auto"][0]


def test_refresh_from_project_without_weight_manager_returns_dash_caption():
    project_manager = MagicMock()
    project_manager.get_project_type.return_value = "pre_recorded"
    project_manager.project_data = {}
    project_manager.get_zone_data.return_value = None

    panel = _bare_panel(project_manager=project_manager, weight_manager=None)
    panel.refresh_from_project()

    cast(MagicMock, panel._model_label).config.assert_called_with(text="Modelo do aquário: —")
