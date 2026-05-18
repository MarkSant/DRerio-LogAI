"""Tests for ``ProjectInitializer.initialize_live_components`` camera lifecycle.

Focused on the bug where the project-load Camera handle stayed alive for
the entire session, leaving the physical device powered on (LED-on) and
conflicting with the calibration camera during auto-detect.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, patch

from zebtrack.ui.components.project_initializer import ProjectInitializer


def _make_gui_stub() -> Any:
    """Build a GUI stub with the minimum surface ProjectInitializer touches."""
    settings = MagicMock()
    settings.arduino.port = ""
    settings.camera.index = 0
    settings_copy = MagicMock()
    settings_copy.camera = SimpleNamespace(index=0)
    settings.model_copy.return_value = settings_copy

    hardware_vm = SimpleNamespace(
        arduino=None,
        camera=None,
        active_frame_source=None,
        detector=MagicMock(),
    )

    controller = SimpleNamespace(settings=settings, hardware_vm=hardware_vm)
    gui = SimpleNamespace(
        controller=controller,
        root=MagicMock(),
        widget_factory=MagicMock(),
        dialog_manager=MagicMock(),
        event_bus=MagicMock(),
    )
    return gui


def _make_pm(camera_index: int = 0, friendly_name: str = "") -> Any:
    pm = MagicMock()
    pm.project_data = {
        "camera_index": camera_index,
        "camera_friendly_name": friendly_name,
        "use_arduino": False,
    }
    pm.get_project_name.return_value = "TestProject"
    return pm


def test_initialize_live_components_releases_camera_immediately():
    """The camera opened to read its native resolution must be released
    before the method returns. Otherwise the device LED stays on for the
    whole project session and conflicts with the calibration camera during
    auto-detect."""
    gui = _make_gui_stub()
    pm = _make_pm()
    initializer = ProjectInitializer(gui)

    fake_camera = MagicMock()
    fake_camera.actual_width = 1920
    fake_camera.actual_height = 1080

    with (
        patch(
            "zebtrack.io.camera.Camera",
            return_value=fake_camera,
        ) as camera_cls,
        patch(
            "zebtrack.core.services.wizard_service.WizardService.resolve_camera_index",
            return_value=(0, "OK"),
        ),
    ):
        initializer.initialize_live_components(pm)

    camera_cls.assert_called_once()
    fake_camera.release.assert_called_once()


def test_initialize_live_components_clears_hardware_vm_references():
    """After init, ``hardware_vm.camera`` and ``active_frame_source`` must be
    None so downstream consumers (e.g. ``_release_preview_camera_if_any``)
    don't try to release a stale handle."""
    gui = _make_gui_stub()
    pm = _make_pm()
    initializer = ProjectInitializer(gui)

    fake_camera = MagicMock()
    fake_camera.actual_width = 640
    fake_camera.actual_height = 480

    with (
        patch("zebtrack.io.camera.Camera", return_value=fake_camera),
        patch(
            "zebtrack.core.services.wizard_service.WizardService.resolve_camera_index",
            return_value=(0, "OK"),
        ),
    ):
        initializer.initialize_live_components(pm)

    assert gui.controller.hardware_vm.camera is None
    assert gui.controller.hardware_vm.active_frame_source is None


def test_initialize_live_components_updates_detector_scaling_with_actual_dims():
    """The whole point of opening the camera is to feed actual_width/height
    into ``detector.update_scaling`` — verify those dims flow through."""
    gui = _make_gui_stub()
    pm = _make_pm()
    initializer = ProjectInitializer(gui)

    fake_camera = MagicMock()
    fake_camera.actual_width = 1280
    fake_camera.actual_height = 720

    with (
        patch("zebtrack.io.camera.Camera", return_value=fake_camera),
        patch(
            "zebtrack.core.services.wizard_service.WizardService.resolve_camera_index",
            return_value=(0, "OK"),
        ),
    ):
        initializer.initialize_live_components(pm)

    gui.controller.hardware_vm.detector.update_scaling.assert_called_once_with(1280, 720)


def test_initialize_live_components_releases_even_if_update_scaling_raises():
    """If detector.update_scaling raises, the camera must still be released
    (no leaked LED-on handle)."""
    gui = _make_gui_stub()
    pm = _make_pm()
    initializer = ProjectInitializer(gui)

    gui.controller.hardware_vm.detector.update_scaling.side_effect = RuntimeError("scaling failed")

    fake_camera = MagicMock()
    fake_camera.actual_width = 640
    fake_camera.actual_height = 480

    with (
        patch("zebtrack.io.camera.Camera", return_value=fake_camera),
        patch(
            "zebtrack.core.services.wizard_service.WizardService.resolve_camera_index",
            return_value=(0, "OK"),
        ),
    ):
        try:
            initializer.initialize_live_components(pm)
        except RuntimeError:
            pass

    fake_camera.release.assert_called_once()


def test_initialize_live_components_swallows_release_failure():
    """If the underlying ``release()`` raises (e.g. driver hiccup) the init
    must still complete and clear ``hardware_vm.camera``."""
    gui = _make_gui_stub()
    pm = _make_pm()
    initializer = ProjectInitializer(gui)

    fake_camera = MagicMock()
    fake_camera.actual_width = 640
    fake_camera.actual_height = 480
    fake_camera.release.side_effect = RuntimeError("driver hiccup")

    with (
        patch("zebtrack.io.camera.Camera", return_value=fake_camera),
        patch(
            "zebtrack.core.services.wizard_service.WizardService.resolve_camera_index",
            return_value=(0, "OK"),
        ),
    ):
        initializer.initialize_live_components(pm)

    assert gui.controller.hardware_vm.camera is None
    assert gui.controller.hardware_vm.active_frame_source is None
    fake_camera.release.assert_called_once()


def test_initialize_live_components_shows_warning_when_camera_missing():
    """``MISSING`` status from the resolver must surface a user-visible warning
    before continuing to open the fallback index."""
    gui = _make_gui_stub()
    pm = _make_pm(camera_index=2, friendly_name="GhostCam")
    initializer = ProjectInitializer(gui)

    fake_camera = MagicMock()
    fake_camera.actual_width = 640
    fake_camera.actual_height = 480

    with (
        patch("zebtrack.io.camera.Camera", return_value=fake_camera),
        patch(
            "zebtrack.core.services.wizard_service.WizardService.resolve_camera_index",
            return_value=(2, "MISSING"),
        ),
    ):
        initializer.initialize_live_components(pm)

    cast(MagicMock, gui.dialog_manager.show_warning).assert_called_once()
    # Camera was still opened (fallback) and released cleanly.
    fake_camera.release.assert_called_once()
    assert gui.controller.hardware_vm.camera is None


def test_initialize_live_components_publishes_video_tree_refresh():
    """The video selector tree in the Zone Configuration tab must be told to
    refresh on live-project load (mirroring the pre-recorded path). Without
    this event the tree stays empty even when the project already has
    completed sessions registered as videos."""
    from zebtrack.ui.event_bus_v2 import UIEvents

    gui = _make_gui_stub()
    pm = _make_pm()
    initializer = ProjectInitializer(gui)

    fake_camera = MagicMock()
    fake_camera.actual_width = 640
    fake_camera.actual_height = 480

    with (
        patch("zebtrack.io.camera.Camera", return_value=fake_camera),
        patch(
            "zebtrack.core.services.wizard_service.WizardService.resolve_camera_index",
            return_value=(0, "OK"),
        ),
    ):
        initializer.initialize_live_components(pm)

    published_types = [
        getattr(call.args[0], "type", None)
        for call in cast(MagicMock, gui.event_bus.publish).call_args_list
    ]
    assert UIEvents.VIDEO_TREE_REFRESH_REQUESTED in published_types, (
        "live-project init must publish VIDEO_TREE_REFRESH_REQUESTED so the "
        "Zone tab's video selector tree populates"
    )
