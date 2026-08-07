"""Decisão única sobre capturar máscaras de segmentação durante a gravação.

Capturar máscara custa tempo de inferência A CADA FRAME e produz um arquivo a
mais por vídeo. Três condições precisam valer ao mesmo tempo para que isso se
pague, e elas moram em lugares diferentes da configuração:

1. ``recorder.persist_masks`` — o operador pediu.
2. ``model_selection.animal_method == "seg"`` — existe modelo capaz de máscara.
   Com um modelo ``det`` não há o que decodificar, e ligar a captura só
   gastaria uma chamada por frame para receber lista vazia.
3. A regra de ROI efetiva é ``seg_overlap`` — alguém vai LER o resultado.

Nenhuma das três sozinha basta, e espalhar a conjunção pelos três pipelines de
gravação garantiria que eles divergissem. O módulo é puro: sem I/O, sem
singleton.
"""

from __future__ import annotations

from typing import Any

import structlog

from zebtrack.core.services.roi_rule_resolver import resolve_roi_rule

log = structlog.get_logger()

__all__ = ["should_capture_masks"]


def should_capture_masks(settings_obj: Any, project_data: Any = None) -> bool:
    """Se esta sessão deve decodificar e persistir máscaras.

    Args:
        settings_obj: instância de ``Settings`` injetada (ou ``None``).
        project_data: ``ProjectManager.project_data``, para que um override de
            ``roi_settings`` do projeto conte na decisão — é a mesma
            precedência que o relatório vai usar depois. Sem isso, um projeto
            configurado com ``seg_overlap`` sobre um global ``bbox_intersects``
            gravaria sem máscaras e degradaria no relatório.

    Returns:
        ``False`` em qualquer dúvida. O custo de não gravar é um aviso de
        degradação no relatório; o de gravar sem necessidade é tempo de
        inferência em toda sessão.
    """
    if settings_obj is None:
        return False

    recorder_settings = getattr(settings_obj, "recorder", None)
    if not bool(getattr(recorder_settings, "persist_masks", False)):
        return False

    model_selection = getattr(settings_obj, "model_selection", None)
    if str(getattr(model_selection, "animal_method", "det")).strip().lower() != "seg":
        log.warning(
            "mask_capture.disabled.detection_model",
            reason=(
                "recorder.persist_masks está ligado, mas o modelo do animal é "
                "'det' e não produz máscara. A regra seg_overlap vai degradar "
                "para bbox_intersects no relatório."
            ),
        )
        return False

    rule = resolve_roi_rule(project_data, settings_obj).rule
    if rule != "seg_overlap":
        log.info("mask_capture.disabled.rule_does_not_use_masks", rule=rule)
        return False

    return True
