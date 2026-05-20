"""Tests for ``ProjectInitializer.initialize_live_components`` camera lifecycle.

Focused on the bug where the project-load Camera handle stayed alive for
the entire session, leaving the physical device powered on (LED-on) and
conflicting with the calibration camera during auto-detect.

Etapa 10b clarification: the project-init flow no longer opens a Camera
at all. The previous version opened one solely to call a now-deleted
``detector.update_scaling(w, h)`` API; that method was renamed to
``set_zones(zones, w, h)`` long ago and is invoked at zone-definition
time (auto-detect / manual draw), not at project init. So the tests
verify the *absence* of any Camera() instantiation here, and the
preservation of the legacy hardware_vm.camera = None bookkeeping.
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


def test_initialize_live_components_does_not_open_camera():
    """The device must NOT be opened at project-init time. Opening it here
    used to (a) leave the LED on for the whole project session and
    (b) conflict with the calibration camera during auto-detect."""
    gui = _make_gui_stub()
    pm = _make_pm()
    initializer = ProjectInitializer(gui)

    with (
        patch("zebtrack.io.camera.Camera") as camera_cls,
        patch(
            "zebtrack.core.services.wizard_service.WizardService.resolve_camera_index",
            return_value=(0, "OK"),
        ),
    ):
        initializer.initialize_live_components(pm)

    camera_cls.assert_not_called()


def test_initialize_live_components_does_not_call_deleted_update_scaling():
    """``detector.update_scaling(w, h)`` was a real-world AttributeError —
    the method was renamed to ``set_zones``. Calling it crashed brand-new
    live-project creation. Verify the call is gone."""
    gui = _make_gui_stub()
    pm = _make_pm()
    initializer = ProjectInitializer(gui)

    with patch(
        "zebtrack.core.services.wizard_service.WizardService.resolve_camera_index",
        return_value=(0, "OK"),
    ):
        initializer.initialize_live_components(pm)

    cast(MagicMock, gui.controller.hardware_vm.detector.update_scaling).assert_not_called()


def test_initialize_live_components_clears_hardware_vm_references():
    """After init, ``hardware_vm.camera`` and ``active_frame_source`` must be
    None so downstream consumers (e.g. ``_release_preview_camera_if_any``)
    don't try to release a stale handle."""
    gui = _make_gui_stub()
    # Seed legacy non-None values to confirm they get cleared.
    gui.controller.hardware_vm.camera = MagicMock()
    gui.controller.hardware_vm.active_frame_source = MagicMock()
    pm = _make_pm()
    initializer = ProjectInitializer(gui)

    with patch(
        "zebtrack.core.services.wizard_service.WizardService.resolve_camera_index",
        return_value=(0, "OK"),
    ):
        initializer.initialize_live_components(pm)

    assert gui.controller.hardware_vm.camera is None
    assert gui.controller.hardware_vm.active_frame_source is None


def test_initialize_live_components_shows_warning_when_camera_missing():
    """``MISSING`` status from the resolver must surface a user-visible warning
    even though we no longer open the device to verify it."""
    gui = _make_gui_stub()
    pm = _make_pm(camera_index=2, friendly_name="GhostCam")
    initializer = ProjectInitializer(gui)

    with patch(
        "zebtrack.core.services.wizard_service.WizardService.resolve_camera_index",
        return_value=(2, "MISSING"),
    ):
        initializer.initialize_live_components(pm)

    cast(MagicMock, gui.dialog_manager.show_warning).assert_called_once()
    # Even on MISSING the bookkeeping must be clean.
    assert gui.controller.hardware_vm.camera is None
    assert gui.controller.hardware_vm.active_frame_source is None


def test_initialize_live_components_publishes_video_tree_refresh():
    """The video selector tree in the Zone Configuration tab must be told to
    refresh on live-project load (mirroring the pre-recorded path). Without
    this event the tree stays empty even when the project already has
    completed sessions registered as videos."""
    from zebtrack.ui.event_bus_v2 import UIEvents

    gui = _make_gui_stub()
    pm = _make_pm()
    initializer = ProjectInitializer(gui)

    with patch(
        "zebtrack.core.services.wizard_service.WizardService.resolve_camera_index",
        return_value=(0, "OK"),
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


def test_initialize_live_components_skips_arduino_when_disabled():
    """Project opts out of Arduino → arduino_manager.connect() must NOT fire.
    Guards against regression of the prior crash where the connect call ran
    even when use_arduino=False (Etapa 6 polish)."""
    gui = _make_gui_stub()
    arduino_manager = MagicMock()
    gui.controller.hardware_vm.arduino = arduino_manager
    pm = _make_pm()  # use_arduino=False by default
    initializer = ProjectInitializer(gui)

    with patch(
        "zebtrack.core.services.wizard_service.WizardService.resolve_camera_index",
        return_value=(0, "OK"),
    ):
        initializer.initialize_live_components(pm)

    arduino_manager.connect.assert_not_called()
