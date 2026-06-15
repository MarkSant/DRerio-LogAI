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


def test_load_project_view_does_not_auto_prompt_arena_calibration_for_live():
    """Live projects with no arena defined must NOT trigger the
    "configurar calibração agora?" auto-prompt at project-open time.
    Calibration belongs to the per-session flow (``ensure_zones_before_recording``
    fires when the user clicks "Iniciar Sessão"). The previous auto-prompt
    implied a single global arena exists for the whole project, contradicting
    the live workflow where each recording can have its own aquarium setup.

    Implementation note: ``load_project_view`` touches a wide GUI surface
    (notebook, tab_builder, analysis_display_widget, …). Mocking all of it
    is brittle, so this test patches ``initialize_live_components`` and
    ``initialize_prerecorded_components`` to no-ops and then drives the
    final stretch of ``load_project_view`` by hand to verify that no
    ``check_live_project_calibration`` scheduling happens for live projects.
    """
    gui = MagicMock()
    pm = MagicMock()
    pm.get_project_type.return_value = "live"
    pm.get_project_name.return_value = "TestLive"
    pm.project_data = {
        "camera_index": 0,
        "camera_friendly_name": "",
        "use_arduino": False,
    }
    gui.controller.project_manager = pm

    # Reset any auto-instantiated child mocks so we can assert call_args cleanly.
    gui.root.after.reset_mock()
    gui.validation_manager.check_live_project_calibration.reset_mock()

    initializer = ProjectInitializer(gui)

    with (
        patch.object(initializer, "initialize_live_components"),
        patch.object(initializer, "initialize_prerecorded_components"),
        patch.object(initializer, "create_main_control_frame"),
        patch.object(initializer, "update_window_title"),
        patch.object(initializer, "restore_persisted_project_settings"),
    ):
        initializer.load_project_view()

    # No ``root.after`` call should have ``check_live_project_calibration``
    # as its scheduled callback. (Other delayed work via ``root.after`` is
    # fine — we only forbid that specific scheduling.)
    for call in gui.root.after.call_args_list:
        cb = call.args[1] if len(call.args) >= 2 else None
        assert cb is not gui.validation_manager.check_live_project_calibration, (
            "Live-project load must not schedule the arena calibration "
            "auto-prompt; calibration is per-session, not per-project"
        )
    gui.validation_manager.check_live_project_calibration.assert_not_called()


def test_create_main_control_frame_tears_down_existing_notebook():
    """Idempotência (Issue 2): com um notebook já presente (fluxo de vídeo
    único ao vivo SEM projeto, que monta a view tardiamente), uma 2ª chamada
    deve DERRUBAR o antigo via ``_destroy_notebook_and_main_controls`` em vez de
    empilhar um segundo ``ttk.Notebook`` no root (fileira de abas fantasma)."""
    gui = MagicMock()
    gui.welcome_frame = None
    gui.status_frame = None
    gui.notebook = MagicMock()  # notebook já existe
    gui.controller.project_manager.get_project_type.return_value = None

    initializer = ProjectInitializer(gui)

    with (
        patch("zebtrack.ui.components.project_initializer.ttk"),
        patch("zebtrack.ui.components.project_initializer.Label"),
        patch("zebtrack.ui.components.project_initializer.reset_geometry_if_not_maximized"),
    ):
        initializer.create_main_control_frame()

    cast(MagicMock, gui.state_synchronizer._destroy_notebook_and_main_controls).assert_called_once()


def test_create_main_control_frame_no_teardown_on_first_build():
    """Primeira montagem (notebook None) NÃO deve chamar o teardown — só a
    construção. Evita destruir/reconstruir desnecessariamente no caminho feliz."""
    gui = MagicMock()
    gui.welcome_frame = None
    gui.status_frame = None
    gui.notebook = None  # primeira montagem
    gui.controller.project_manager.get_project_type.return_value = None

    initializer = ProjectInitializer(gui)

    with (
        patch("zebtrack.ui.components.project_initializer.ttk"),
        patch("zebtrack.ui.components.project_initializer.Label"),
        patch("zebtrack.ui.components.project_initializer.reset_geometry_if_not_maximized"),
    ):
        initializer.create_main_control_frame()

    cast(MagicMock, gui.state_synchronizer._destroy_notebook_and_main_controls).assert_not_called()


def test_restore_persisted_project_settings_parses_string_false_preview_flag():
    """Persisted preview flags may come back as strings from older project data.

    "False" must restore to False instead of following Python truthiness for
    non-empty strings.
    """
    gui = MagicMock()
    gui.show_preview_var = MagicMock()
    gui.processing_interval_var = MagicMock()
    gui.analysis_interval_var = MagicMock()
    gui.display_interval_var = MagicMock()

    pm = MagicMock()
    pm.project_data = {"last_show_preview": "False"}

    initializer = ProjectInitializer(gui)

    initializer.restore_persisted_project_settings(pm)

    gui.show_preview_var.set.assert_called_once_with(False)
