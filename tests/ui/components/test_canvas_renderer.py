from types import SimpleNamespace
from unittest.mock import Mock

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
