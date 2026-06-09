"""Preparação da aba "Análise" para sessões ao vivo — lógica compartilhada.

Extraído de ``LiveCameraSessionCoordinator._prepare_analysis_tab_for_live_session``
para que TODOS os coordinators que despacham para ``LiveCameraService.start_session``
com preview integrado (``use_external_preview=False``) executem a mesma preparação:

  - ``LiveCameraSessionCoordinator`` (3 entrypoints: ``start_live_session``,
    ``start_session_from_config`` e ``start_live_project_session``);
  - ``RecordingSessionCoordinator._schedule_recording`` (gravação temporizada de
    projeto live retomada via confirmação de zonas — ``_on_zone_saved``).

Sem esta preparação a 2ª gravação recebe os frames mas o preview fica congelado:
o canvas foi desinscrito de UI_UPDATE_LIVE_FRAME no stop anterior e
``gui.analysis_active`` foi desligado pela pós-análise do vídeo anterior.

Funções livres (recebem ``view``/``root`` em vez de injetar um coordinator) para
evitar dependência circular no DI: ``RecordingSessionCoordinator`` é construído
ANTES de ``LiveCameraSessionCoordinator`` em ``di_registrations``.
"""

from __future__ import annotations

from typing import Any

import structlog

log = structlog.get_logger()


def prepare_analysis_tab_for_live_session(view: Any, root: Any) -> None:
    """Prepara a aba "Análise" para QUALQUER nova sessão ao vivo.

    Faz três coisas:
      1. zera os contadores exibidos (Total/Processados/Detectados/Tempo);
      2. re-inscreve o canvas em UI_UPDATE_LIVE_FRAME;
      3. religa ``gui.analysis_active`` e reabre a aba de análise.

    Args:
        view: Instância da GUI (``ApplicationGUI``) ou None em modo headless.
        root: Root Tkinter para agendar via ``after(0, ...)`` ou None
            (execução síncrona — testes/headless).
    """
    reset_live_progress_display(view, root)
    resubscribe_canvas_live_frames(view)
    activate_live_analysis_view(view, root)


def reset_live_progress_display(view: Any, root: Any) -> None:
    """Zera os contadores de progresso da aba Análise para uma nova sessão.

    Sem isto, ao iniciar a 2ª gravação live os rótulos Total/Processados/
    Detectados/Tempo continuam mostrando os números finais da 1ª sessão até
    a primeira atualização de stats da nova sessão.
    """
    widget = getattr(view, "analysis_display_widget", None) if view else None
    if widget is None or not hasattr(widget, "reset_progress_stats"):
        return
    if root is not None:
        root.after(0, widget.reset_progress_stats)
    else:
        widget.reset_progress_stats()


def resubscribe_canvas_live_frames(view: Any) -> None:
    """Re-inscreve o canvas em UI_UPDATE_LIVE_FRAME para a nova sessão.

    A inscrição é idempotente (ver ``CanvasManager.subscribe_to_live_frames``)
    e é necessária porque ``_finalize_live_session_ui`` desinscreve o canvas
    a cada stop; sem re-inscrever no start, o preview ao vivo para de
    atualizar a partir da 2ª sessão.
    """
    if (
        view
        and hasattr(view, "canvas_manager")
        and hasattr(view.canvas_manager, "subscribe_to_live_frames")
    ):
        view.canvas_manager.subscribe_to_live_frames()
        log.info("live_session_ui_prep.canvas_resubscribed")


def activate_live_analysis_view(view: Any, root: Any) -> None:
    """Garante que o modo de análise está ativo para renderizar o preview.

    ``VideoFrameManager.update_video_frame`` só desenha o frame ao vivo
    quando ``gui.analysis_active`` é True. A pós-análise do vídeo anterior
    concluído com sucesso chama ``stop_analysis_view_mode`` — que desliga
    ``analysis_active`` e volta para a aba de zonas — então cada nova sessão
    precisa religar a flag e reabrir a aba de análise. Sem isto, a 2ª
    gravação recebe os frames (canvas re-inscrito) mas não os exibe.
    """
    if view is None:
        return
    controller = getattr(view, "analysis_view_controller", None)

    def _apply() -> None:
        try:
            view.analysis_active = True
            if controller is not None and hasattr(controller, "switch_to_analysis_view"):
                controller.switch_to_analysis_view()
            log.info("live_session_ui_prep.analysis_view_activated")
        # except Exception justified: never let UI activation abort the start
        except Exception:
            log.debug(
                "live_session_ui_prep.activate_analysis_view.failed",
                exc_info=True,
            )

    if root is not None:
        root.after(0, _apply)
    else:
        _apply()
