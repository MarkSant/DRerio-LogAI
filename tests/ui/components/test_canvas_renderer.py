from types import SimpleNamespace
from unittest.mock import Mock, patch

from zebtrack.ui.components.canvas.renderer import CanvasRenderer


def _make_renderer(gui_overrides=None, manager_overrides=None):
    gui_data = {"video_display": None}
    if gui_overrides:
        gui_data.update(gui_overrides)
    gui = SimpleNamespace(**gui_data)

    manager_data = {"gui": gui}
    if manager_overrides:
        manager_data.update(manager_overrides)
    manager = SimpleNamespace(**manager_data)
    return CanvasRenderer(manager)


def test_get_canvas_no_video_display():
    renderer = _make_renderer()

    assert renderer._get_canvas() is None


def test_get_canvas_no_canvas():
    video_display = SimpleNamespace(canvas=None)
    renderer = _make_renderer(gui_overrides={"video_display": video_display})

    assert renderer._get_canvas() is None


def test_get_canvas_widget_destroyed():
    canvas = Mock()
    canvas.winfo_exists.return_value = False
    video_display = SimpleNamespace(canvas=canvas)
    renderer = _make_renderer(gui_overrides={"video_display": video_display})

    assert renderer._get_canvas() is None


def test_clear_zone_elements_deletes_tags():
    renderer = _make_renderer()
    canvas = Mock()

    renderer._clear_zone_elements(canvas)

    expected_tags = [
        "main_polygon",
        "roi_polygon",
        "roi_label",
        "roi_label_bg",
        "elastic_line",
        "drawing_aid",
        "temp_vertex",
        "geotaxis_zone",
    ]
    for tag in expected_tags:
        canvas.delete.assert_any_call(tag)


def test_ensure_background_restores_when_missing():
    canvas = Mock()
    canvas.find_withtag.return_value = []
    renderer = _make_renderer(manager_overrides={"_canvas_bg_image": object()})
    renderer._restore_background_image = Mock()

    renderer._ensure_background(canvas)

    renderer._restore_background_image.assert_called_once_with(canvas)


def test_ensure_background_skips_when_present():
    canvas = Mock()
    canvas.find_withtag.return_value = [1]
    renderer = _make_renderer(manager_overrides={"_canvas_bg_image": object()})
    renderer._restore_background_image = Mock()

    renderer._ensure_background(canvas)

    renderer._restore_background_image.assert_not_called()


def test_ensure_background_loads_frame_when_missing_bg_image():
    canvas = Mock()
    manager_overrides = {"_canvas_bg_image": None, "load_video_frame_to_canvas": Mock()}
    renderer = _make_renderer(manager_overrides=manager_overrides)

    renderer._ensure_background(canvas)

    renderer.manager.load_video_frame_to_canvas.assert_called_once()


def test_redraw_zones_defers_polygons_without_background_geometry():
    canvas = Mock()
    video_display = SimpleNamespace(canvas=canvas)
    manager_overrides = {
        "_canvas_bg_image": None,
        "_raw_bg_image": None,
        "_bg_scale": None,
        "_bg_offset": None,
        "load_video_frame_to_canvas": Mock(return_value=False),
    }
    renderer = _make_renderer(
        gui_overrides={"video_display": video_display}, manager_overrides=manager_overrides
    )
    renderer._draw_single_aquarium_zones = Mock()

    renderer.redraw_zones(SimpleNamespace(polygon=[[0, 0], [1, 0], [1, 1]], roi_polygons=[]))

    renderer.manager.load_video_frame_to_canvas.assert_called_once()
    renderer._draw_single_aquarium_zones.assert_not_called()


def test_restore_background_image_uses_position():
    canvas = Mock()
    renderer = _make_renderer(
        manager_overrides={
            "_canvas_bg_image": object(),
            "_canvas_bg_position": (100, 200, "center"),
        }
    )

    renderer._restore_background_image(canvas)

    canvas.create_image.assert_called_once_with(
        100,
        200,
        anchor="center",
        image=renderer.manager._canvas_bg_image,
        tags="background_image",
    )
    canvas.tag_lower.assert_called_once_with("background_image")


def _placeholder_renderer(canvas_size=(800, 600), **manager_overrides):
    """Renderer over a mocked canvas with no frame displayed."""
    canvas = Mock()
    canvas.winfo_width.return_value = canvas_size[0]
    canvas.winfo_height.return_value = canvas_size[1]
    video_display = SimpleNamespace(canvas=canvas)
    base = {
        "_canvas_bg_image": None,
        "_raw_bg_image": None,
        "_bg_scale": None,
        "_bg_offset": None,
        "_canvas_placeholder_image": None,
    }
    base.update(manager_overrides)
    renderer = _make_renderer(
        gui_overrides={"video_display": video_display, "root": Mock()},
        manager_overrides=base,
    )
    return renderer, canvas


def test_draw_placeholder_logo_draws_logo_and_caption():
    renderer, canvas = _placeholder_renderer()

    with patch("zebtrack.ui.components.canvas.renderer.ImageTk"):
        renderer.draw_placeholder_logo()

    tags = [call.kwargs.get("tags") for call in canvas.create_image.call_args_list]
    assert tags == [CanvasRenderer.PLACEHOLDER_TAG]
    assert canvas.create_text.call_count == 1
    assert canvas.create_text.call_args.kwargs["tags"] == CanvasRenderer.PLACEHOLDER_TAG
    assert renderer.manager._canvas_placeholder_image is not None


def test_draw_placeholder_logo_leaves_coordinate_mapping_unset():
    """The placeholder must not masquerade as a displayed frame.

    ``_has_background_geometry`` gates zone drawing on these attributes; if the
    logo filled them in, ROI polygons would be projected onto it using a scale
    that belongs to no video.
    """
    renderer, _canvas = _placeholder_renderer()

    with patch("zebtrack.ui.components.canvas.renderer.ImageTk"):
        renderer.draw_placeholder_logo()

    assert renderer.manager._raw_bg_image is None
    assert renderer.manager._canvas_bg_image is None
    assert renderer.manager._bg_scale is None
    assert renderer.manager._bg_offset is None
    assert renderer._has_background_geometry() is False


def test_draw_placeholder_logo_never_wipes_a_displayed_frame():
    renderer, canvas = _placeholder_renderer(
        _canvas_bg_image=object(),
        _raw_bg_image=object(),
        _bg_scale=1.0,
        _bg_offset=(0, 0),
    )

    with patch("zebtrack.ui.components.canvas.renderer.ImageTk"):
        renderer.draw_placeholder_logo()

    canvas.create_image.assert_not_called()
    canvas.create_text.assert_not_called()
    canvas.delete.assert_not_called()


def test_draw_placeholder_logo_retries_before_canvas_has_geometry():
    renderer, canvas = _placeholder_renderer(canvas_size=(1, 1))

    with patch("zebtrack.ui.components.canvas.renderer.ImageTk"):
        renderer.draw_placeholder_logo()

    canvas.create_image.assert_not_called()
    assert renderer.gui.root.after.call_args.args[0] == CanvasRenderer.PLACEHOLDER_RETRY_DELAY_MS


def test_draw_placeholder_logo_gives_up_on_a_canvas_that_never_sizes():
    """A hidden notebook tab never gains geometry.

    An unbounded retry would then reschedule itself for the whole session; the
    canvas <Configure> fired when the tab is finally shown asks again anyway.
    """
    renderer, _canvas = _placeholder_renderer(canvas_size=(1, 1))
    root = renderer.gui.root
    # Drive the retry chain the way Tk would: run whatever `after` scheduled.
    with patch("zebtrack.ui.components.canvas.renderer.ImageTk"):
        renderer.draw_placeholder_logo()
        for _ in range(CanvasRenderer.PLACEHOLDER_RETRY_LIMIT + 5):
            if not root.after.call_args_list:
                break
            scheduled = root.after.call_args.args[1]
            root.after.reset_mock()
            scheduled()

    assert root.after.call_args_list == []


def test_clear_placeholder_logo_drops_tag_and_reference():
    renderer, canvas = _placeholder_renderer(_canvas_placeholder_image=object())

    renderer.clear_placeholder_logo()

    canvas.delete.assert_called_once_with(CanvasRenderer.PLACEHOLDER_TAG)
    assert renderer.manager._canvas_placeholder_image is None


def _overlay_renderer():
    canvas = Mock()
    canvas.winfo_exists.return_value = True
    renderer = _make_renderer(
        gui_overrides={
            "video_display": SimpleNamespace(canvas=canvas),
            "analysis_active": False,
            "notebook": None,
        },
        manager_overrides={"_video_to_canvas": lambda x, y: (x, y)},
    )
    return renderer, canvas


def _drawn(canvas):
    rects = [c.kwargs["outline"] for c in canvas.create_rectangle.call_args_list]
    texts = [(c.kwargs["text"], c.kwargs["fill"]) for c in canvas.create_text.call_args_list]
    return rects, texts


def test_update_overlay_legacy_colours_without_a_role_map():
    renderer, canvas = _overlay_renderer()

    renderer.update_overlay([(0, 0, 9, 9, 0.9, 1, 0), (1, 1, 5, 5, 0.8, 2, 1)])

    assert _drawn(canvas) == (["yellow", "cyan"], [("ID: 1", "yellow"), ("ID: 2", "cyan")])


def test_update_overlay_single_subject_label_is_translatable_target():
    renderer, canvas = _overlay_renderer()

    renderer.update_overlay([(1, 1, 5, 5, 0.8, 2, 1)], is_single_subject=True)

    assert _drawn(canvas) == (["magenta"], [("Target", "magenta")])


def test_update_overlay_colours_by_role_with_an_explicit_map():
    renderer, canvas = _overlay_renderer()

    renderer.update_overlay(
        [(0, 0, 9, 9, 0.9, 7, 0), (1, 1, 5, 5, 0.8, None, 1), (2, 2, 4, 4, 0.7, None, 2)],
        class_roles={0: "subject", 1: "context", 2: "arena"},
        class_names={1: "experimenter"},
    )

    assert _drawn(canvas) == (
        ["cyan", "orange", "yellow"],
        [("ID: 7", "cyan"), ("experimenter", "orange"), ("Arena", "yellow")],
    )
