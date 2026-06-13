"""Regression tests for SingleVideoWorkflow.on_auto_detect_clicked.

Garante que a auto-detecção multi-aquário no fluxo de vídeo único usa o número
de aquários do CONFIG submetido pelo usuário (``pending_single_video_config``),
e não o cache global ``settings.analysis_config.num_aquariums`` — que pode ser
ressincronizado para a contagem do projeto (default 1) quando a UI é montada,
fazendo a detecção cair em modo single mesmo com o usuário pedindo 2 aquários.
"""

from types import SimpleNamespace
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
