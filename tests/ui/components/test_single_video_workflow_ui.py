"""UI-level regression tests for SingleVideoWorkflow.

Two topics live here, both driven through stub GUIs rather than a real Tk tree.

``_start_single_video_processing`` must leave the start button clickable when
the coordinator refuses the run — the event bus swallows handler exceptions and
the coordinator has four handled early returns, and nothing navigates back to
the welcome screen that would recreate the button.

``on_auto_detect_clicked``

Garante que a auto-detecção multi-aquário no fluxo de vídeo único usa o número
de aquários do CONFIG submetido pelo usuário (``pending_single_video_config``),
e não o cache global ``settings.analysis_config.num_aquariums`` — que pode ser
ressincronizado para a contagem do projeto (default 1) quando a UI é montada,
fazendo a detecção cair em modo single mesmo com o usuário pedindo 2 aquários.
"""

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock

from zebtrack.ui.components.single_video_workflow import SingleVideoWorkflow
from zebtrack.ui.event_bus_v2 import UIEvents


def _auto_detect_gui(*, pending_config, settings_num_aq):
    """gui stub mínimo para on_auto_detect_clicked."""
    pm = Mock()
    pm.get_active_zone_video.return_value = "C:/videos/exp_2aq.mp4"
    return SimpleNamespace(
        analysis_active=False,
        stabilization_frames_var=SimpleNamespace(get=lambda: "10", set=lambda _v: None),
        canvas_manager=SimpleNamespace(clear_interactive_polygon=lambda: None),
        controller=SimpleNamespace(project_manager=pm),
        pending_single_video_path="C:/videos/exp_2aq.mp4",
        pending_single_video_config=pending_config,
        settings=SimpleNamespace(analysis_config=SimpleNamespace(num_aquariums=settings_num_aq)),
        event_dispatcher=Mock(),
    )


def _published_expected_count(gui):
    call = gui.event_dispatcher.publish_event.call_args
    assert call.args[0] is UIEvents.ZONE_AUTO_DETECT
    return call.args[1].expected_count


def test_auto_detect_prefers_pending_config_over_reset_settings():
    """Usuário pediu 2 aquários; settings foi ressincronizado p/ 1 → detecta 2."""
    gui = _auto_detect_gui(pending_config={"num_aquariums": 2}, settings_num_aq=1)
    workflow = SingleVideoWorkflow(gui, dialog_manager=Mock())

    workflow.on_auto_detect_clicked()

    assert _published_expected_count(gui) == 2


def test_auto_detect_single_when_pending_config_is_one():
    """Config pendente = 1 → detecção single (expected_count None)."""
    gui = _auto_detect_gui(pending_config={"num_aquariums": 1}, settings_num_aq=2)
    workflow = SingleVideoWorkflow(gui, dialog_manager=Mock())

    workflow.on_auto_detect_clicked()

    assert _published_expected_count(gui) is None


def test_auto_detect_falls_back_to_settings_without_pending_config():
    """Sem config pendente (fluxo de projeto), usa settings."""
    gui = _auto_detect_gui(pending_config=None, settings_num_aq=2)
    workflow = SingleVideoWorkflow(gui, dialog_manager=Mock())

    workflow.on_auto_detect_clicked()

    assert _published_expected_count(gui) == 2


def _live_auto_detect_gui(*, project_type, calibration_coordinator):
    """gui stub para um projeto SEM vídeo (ex.: projeto live)."""
    pm = Mock()
    pm.get_active_zone_video.return_value = None
    pm.get_project_type.return_value = project_type
    controller = SimpleNamespace(
        project_manager=pm,
        live_calibration_coordinator=calibration_coordinator,
    )
    return SimpleNamespace(
        analysis_active=False,
        stabilization_frames_var=SimpleNamespace(get=lambda: "10", set=lambda _v: None),
        canvas_manager=SimpleNamespace(clear_interactive_polygon=lambda: None),
        controller=controller,
        pending_single_video_path=None,
        pending_single_video_config=None,
        settings=SimpleNamespace(analysis_config=SimpleNamespace(num_aquariums=1)),
        event_dispatcher=Mock(),
    )


def _published_event_types(gui):
    return [call.args[0] for call in gui.event_dispatcher.publish_event.call_args_list]


def test_live_project_routes_auto_detect_to_camera():
    """Projeto live sem vídeo → calibração pela câmera, NÃO publica ZONE_AUTO_DETECT."""
    calib = Mock()
    calib.run_live_calibration.return_value = True
    gui = _live_auto_detect_gui(project_type="live", calibration_coordinator=calib)
    workflow = SingleVideoWorkflow(gui, dialog_manager=Mock())

    workflow.on_auto_detect_clicked()

    calib.run_live_calibration.assert_called_once()
    # stabilization_frames deve ser >= 30 (ajuste de exposição da câmera)
    assert calib.run_live_calibration.call_args.kwargs["stabilization_frames"] >= 30
    # Não deve cair no caminho de vídeo (que publica ZONE_AUTO_DETECT).
    assert UIEvents.ZONE_AUTO_DETECT not in _published_event_types(gui)


def test_live_auto_detect_success_refreshes_zone_overlay():
    """Detecção live aprovada → redesenha overlay do polígono (UI_REDRAW_ZONES)."""
    calib = Mock()
    calib.run_live_calibration.return_value = True
    gui = _live_auto_detect_gui(project_type="live", calibration_coordinator=calib)
    workflow = SingleVideoWorkflow(gui, dialog_manager=Mock())

    workflow.on_auto_detect_clicked()

    published = _published_event_types(gui)
    assert UIEvents.UI_REDRAW_ZONES in published
    assert UIEvents.UI_UPDATE_ZONE_LIST in published


def test_live_auto_detect_cancelled_does_not_refresh_overlay():
    """Detecção live cancelada/falha (False) → não redesenha nada."""
    calib = Mock()
    calib.run_live_calibration.return_value = False
    gui = _live_auto_detect_gui(project_type="live", calibration_coordinator=calib)
    workflow = SingleVideoWorkflow(gui, dialog_manager=Mock())

    workflow.on_auto_detect_clicked()

    published = _published_event_types(gui)
    assert UIEvents.UI_REDRAW_ZONES not in published
    assert UIEvents.UI_UPDATE_ZONE_LIST not in published


def test_non_live_project_without_video_does_not_route_to_camera():
    """Projeto batch sem vídeo resolvido não deve chamar a câmera; publica com path vazio."""
    calib = Mock()
    gui = _live_auto_detect_gui(project_type="batch", calibration_coordinator=calib)
    workflow = SingleVideoWorkflow(gui, dialog_manager=Mock())

    workflow.on_auto_detect_clicked()

    calib.run_live_calibration.assert_not_called()
    gui.event_dispatcher.publish_event.assert_called_once()


# ---------------------------------------------------------------------------
# Ad-hoc live (single-video live analysis, NO project)
# ---------------------------------------------------------------------------


def _adhoc_live_gui(*, calibration_coordinator, active_zone_video=None):
    """gui stub para a análise ao vivo de vídeo único: NÃO há projeto.

    ``project_data`` vazio faz ``get_project_type()`` devolver ``None`` e
    ``project_path`` é ``None`` — é isso que distingue este fluxo de um projeto
    live e o que fazia o botão de auto-detectar virar um no-op silencioso.
    """
    pm = Mock()
    pm.get_active_zone_video.return_value = active_zone_video
    pm.get_project_type.return_value = None
    pm.project_path = None
    controller = SimpleNamespace(
        project_manager=pm,
        live_calibration_coordinator=calibration_coordinator,
    )
    return SimpleNamespace(
        analysis_active=False,
        stabilization_frames_var=SimpleNamespace(get=lambda: "10", set=lambda _v: None),
        canvas_manager=SimpleNamespace(clear_interactive_polygon=lambda: None),
        controller=controller,
        pending_single_video_path=None,
        pending_single_video_config=None,
        settings=SimpleNamespace(analysis_config=SimpleNamespace(num_aquariums=1)),
        event_dispatcher=Mock(),
    )


def test_adhoc_live_without_project_routes_auto_detect_to_camera():
    """Sem projeto (vídeo único ao vivo) a auto-detecção TEM de ir para a câmera.

    Regressão: o guard exigia ``project_type == "live"``, mas nesse fluxo não há
    projeto, então o tipo é ``None``. O clique caía em ZONE_AUTO_DETECT com
    ``video_path=""``, que o VideoProcessingCoordinator descarta com um ``return``
    silencioso — sem detecção, sem diálogo e sem erro.
    """
    calib = Mock()
    calib.run_live_calibration.return_value = True
    gui = _adhoc_live_gui(calibration_coordinator=calib)
    workflow = SingleVideoWorkflow(gui, dialog_manager=Mock())

    workflow.on_auto_detect_clicked()

    calib.run_live_calibration.assert_called_once()
    assert UIEvents.ZONE_AUTO_DETECT not in _published_event_types(gui)


def test_redetect_over_live_reference_frame_returns_to_camera():
    """Redetectar após a 1ª calibração não pode tentar abrir o PNG como vídeo.

    Depois da primeira calibração o coordinator define
    ``live_camera_reference_frame.png`` como ``active_zone_video`` (é a chave
    estável de ``zones_by_video``), então ``video_path`` deixa de ser vazio. Sem
    tratar o reference-frame como "sem vídeo", o segundo clique cairia no caminho
    de arquivo e o AquariumDetector tentaria abrir uma imagem como vídeo.
    """
    calib = Mock()
    calib.run_live_calibration.return_value = True
    gui = _adhoc_live_gui(
        calibration_coordinator=calib,
        active_zone_video="C:/tmp/zebtrack_live_adhoc_x/live_camera_reference_frame.png",
    )
    workflow = SingleVideoWorkflow(gui, dialog_manager=Mock())

    workflow.on_auto_detect_clicked()

    calib.run_live_calibration.assert_called_once()
    assert UIEvents.ZONE_AUTO_DETECT not in _published_event_types(gui)


# ---------------------------------------------------------------------------
# The pre-recorded single-video flow ALSO has no project — and must stay on file
# ---------------------------------------------------------------------------


def test_prerecorded_single_video_never_opens_the_camera():
    """No project + a real video file must auto-detect from the FILE.

    This is the load-bearing half of the ``_route_live_auto_detect`` guard, and
    the easiest one to lose. ``is_live_like`` is TRUE here — it is satisfied by
    "no project at all", which the pre-recorded single-video flow also is — so
    the only thing keeping the camera shut is the ``not video_path`` test in
    front of it. Collapse that condition and every single-video auto-detect
    starts grabbing camera frames to look for an aquarium that lives in a file.
    """
    calib = Mock()
    gui = _adhoc_live_gui(
        calibration_coordinator=calib,
        active_zone_video="C:/videos/exp.mp4",
    )
    gui.pending_single_video_path = "C:/videos/exp.mp4"
    gui.pending_single_video_config = {"num_aquariums": 1}
    workflow = SingleVideoWorkflow(gui, dialog_manager=Mock())

    workflow.on_auto_detect_clicked()

    calib.run_live_calibration.assert_not_called()
    assert UIEvents.ZONE_AUTO_DETECT in _published_event_types(gui)


def test_prerecorded_single_video_publishes_the_real_path():
    """The published path must be the file, not an empty string.

    ``VideoProcessingCoordinator`` drops a blank or ``"."`` path with a bare
    ``return``, which is the silent no-op this whole guard exists to prevent.
    """
    gui = _adhoc_live_gui(
        calibration_coordinator=Mock(),
        active_zone_video="C:/videos/exp.mp4",
    )
    gui.pending_single_video_path = "C:/videos/exp.mp4"
    workflow = SingleVideoWorkflow(gui, dialog_manager=Mock())

    workflow.on_auto_detect_clicked()

    payload = gui.event_dispatcher.publish_event.call_args.args[1]
    assert payload.video_path == "C:/videos/exp.mp4"
    assert payload.video_path not in ("", ".")


def test_pending_path_carries_auto_detect_before_zones_are_saved():
    """Falls back to ``pending_single_video_path`` when no active zone video yet.

    Right after the config dialog the video is pending but not yet the active
    zone video, and auto-detect is the very first thing most operators click.
    """
    calib = Mock()
    gui = _adhoc_live_gui(calibration_coordinator=calib, active_zone_video=None)
    gui.pending_single_video_path = "C:/videos/exp.mp4"
    workflow = SingleVideoWorkflow(gui, dialog_manager=Mock())

    workflow.on_auto_detect_clicked()

    calib.run_live_calibration.assert_not_called()
    payload = gui.event_dispatcher.publish_event.call_args.args[1]
    assert payload.video_path == "C:/videos/exp.mp4"


# ---------------------------------------------------------------------------
# ``_start_single_video_processing`` — the start button must survive a failure.
# ---------------------------------------------------------------------------


class _FakeButton:
    """Minimal ttk.Button stand-in that records its state transitions."""

    def __init__(self) -> None:
        self.state = "normal"
        self.history: list[str] = []

    def config(self, **kwargs) -> None:
        if "state" in kwargs:
            self.state = kwargs["state"]
            self.history.append(kwargs["state"])


def _start_gui(*, worker_after_publish, button):
    """gui stub for _start_single_video_processing, no Tk involved.

    ``worker_after_publish`` is what ``processing_coordinator.processing_worker``
    holds once the (synchronous) publish returns — the coordinator sets it just
    before starting the thread on both success paths.
    """
    coordinator = SimpleNamespace(processing_worker=None)

    def _publish(*_args, **_kwargs):
        coordinator.processing_worker = worker_after_publish
        return True

    return SimpleNamespace(
        edited_polygon_points=None,
        pending_single_video_path="C:/videos/exp.mp4",
        pending_single_video_config={"num_aquariums": 1},
        start_single_analysis_btn=button,
        controller=SimpleNamespace(processing_coordinator=coordinator),
        validation_manager=SimpleNamespace(
            compose_single_video_runtime_config=lambda: {"num_aquariums": 1}
        ),
        event_dispatcher=SimpleNamespace(publish_event=_publish),
        dialog_manager=Mock(),
    )


def _drawn_zone_data():
    from zebtrack.core.detection import ZoneData

    return ZoneData(polygon=[[0, 0], [10, 0], [10, 10], [0, 10]])


def test_start_keeps_button_usable_when_coordinator_aborts():
    """A handled abort must not strand the user with a dead button.

    The coordinator has several early returns that only show a dialog (no
    subject on an aquarium, failed validation, unreadable video, no valid video)
    and the event bus swallows any exception raised inside the handler. Before
    this guard, all of them left the button disabled AND the pending state
    cleared, and nothing navigates back to the welcome screen that recreates it.
    """
    button = _FakeButton()
    gui = _start_gui(worker_after_publish=None, button=button)
    workflow = SingleVideoWorkflow(
        gui,
        dialog_manager=Mock(),
        zone_context_service=cast(
            Any,
            SimpleNamespace(get_zone_data_for_active_context=lambda **_kw: _drawn_zone_data()),
        ),
    )

    workflow._start_single_video_processing()

    assert button.state == "normal", "start button must be clickable again after an abort"
    assert gui.pending_single_video_path == "C:/videos/exp.mp4"
    assert gui.pending_single_video_config is not None


def test_start_clears_pending_state_once_worker_is_running():
    """The happy path still hands the run over and drops the pending state."""
    button = _FakeButton()
    gui = _start_gui(worker_after_publish=object(), button=button)
    workflow = SingleVideoWorkflow(
        gui,
        dialog_manager=Mock(),
        zone_context_service=cast(
            Any,
            SimpleNamespace(get_zone_data_for_active_context=lambda **_kw: _drawn_zone_data()),
        ),
    )

    workflow._start_single_video_processing()

    assert button.state == "disabled"
    assert gui.pending_single_video_path is None
    assert gui.pending_single_video_config is None


def test_start_ignores_worker_left_over_from_a_previous_run():
    """Identity, not truthiness: a stale worker is not proof this run started.

    Two single-video runs in one session are now reachable via "Analyse Another
    Video...", so ``processing_worker`` is routinely non-None on entry.
    """
    stale = object()
    button = _FakeButton()
    gui = _start_gui(worker_after_publish=stale, button=button)
    gui.controller.processing_coordinator.processing_worker = stale
    workflow = SingleVideoWorkflow(
        gui,
        dialog_manager=Mock(),
        zone_context_service=cast(
            Any,
            SimpleNamespace(get_zone_data_for_active_context=lambda **_kw: _drawn_zone_data()),
        ),
    )

    workflow._start_single_video_processing()

    assert button.state == "normal"
    assert gui.pending_single_video_path == "C:/videos/exp.mp4"


# ---------------------------------------------------------------------------
# Arena preferences must reach project_data BEFORE auto-detection runs
# ---------------------------------------------------------------------------


def _preferences_workflow(project_data):
    """Workflow whose project_manager exposes ``project_data``."""
    pm = Mock()
    pm.project_data = project_data
    gui = SimpleNamespace(controller=SimpleNamespace(project_manager=pm))
    return SingleVideoWorkflow(
        cast(Any, gui),
        dialog_manager=Mock(),
        zone_context_service=Mock(),
    )


def test_perspective_reaches_project_data_for_arena_detection():
    """The perspective selects the WEIGHT, so it must land before auto-detect.

    It used to reach ``project_data`` only via
    ``_persist_single_video_calibration``, which runs when analysis STARTS. At
    auto-detect time the resolver therefore fell through to the global
    ``settings.behavioral_analysis.aquarium_perspective`` — and a top-down video
    got segmented with the lateral weight.
    """
    project_data: dict = {}
    workflow = _preferences_workflow(project_data)

    workflow._publish_arena_detection_preferences(
        {
            "aquarium_method": "seg",
            "preserve_real_aquarium_shape": True,
            "behavioral_analysis": {"aquarium_perspective": "top_down"},
        }
    )

    assert project_data["behavioral_config"]["aquarium_perspective"] == "top_down"
    assert project_data["model_selection"]["aquarium_method"] == "seg"
    assert project_data["preserve_real_aquarium_shape"] is True


def test_perspective_write_preserves_other_behavioral_keys():
    """Writing the perspective must not wipe a behavioral_config already there."""
    project_data: dict = {"behavioral_config": {"geotaxis_mode": "zones"}}
    workflow = _preferences_workflow(project_data)

    workflow._publish_arena_detection_preferences(
        {"behavioral_analysis": {"aquarium_perspective": "lateral"}}
    )

    assert project_data["behavioral_config"]["aquarium_perspective"] == "lateral"
    assert project_data["behavioral_config"]["geotaxis_mode"] == "zones"


def test_invalid_perspective_degrades_to_the_global_default():
    """A value the weight lookup cannot honour must not be written at all."""
    project_data: dict = {}
    workflow = _preferences_workflow(project_data)

    workflow._publish_arena_detection_preferences(
        {"behavioral_analysis": {"aquarium_perspective": "Top-Down View"}}
    )

    assert "behavioral_config" not in project_data


def test_missing_behavioral_block_is_not_an_error():
    """The dialog can return without a behavioral section; that is not a failure."""
    project_data: dict = {}
    workflow = _preferences_workflow(project_data)

    workflow._publish_arena_detection_preferences({"aquarium_method": "det"})

    assert project_data["model_selection"]["aquarium_method"] == "det"
    assert "behavioral_config" not in project_data
