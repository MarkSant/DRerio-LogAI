"""De onde a pos-analise ao vivo tira os limiares.

O defeito
---------
``_build_post_analysis_service`` montava ``AnalysisService(settings_obj=self.settings)``
-- o objeto COMPARTILHADO, que os dialogos ad-hoc escrevem e nunca restauram.

Numa sessao de PROJETO ao vivo isso significa analisar com os limiares que a
ultima execucao avulsa deixou para tras. E o defeito que o PR #524 mediu no
pre-gravado -- 7 de 9 parametros mudavam num projeto real -- pela porta que
continuava aberta no fluxo ao vivo: ``build_project_settings_snapshot`` tinha
tres pontos de uso, nenhum deles aqui.

Por que os dois casos precisam de fontes diferentes
---------------------------------------------------
Tratar os dois igual quebra um ou outro, e o segundo caso e facil de esquecer:

* **Com projeto**, o snapshot (``projeto > baseline > default``) mantem o objeto
  sujo fora da resposta.
* **Sem projeto**, o objeto vivo. Os valores do dialogo SAO a intencao da
  sessao; o snapshot devolveria o baseline pristino e descartaria calado o que o
  operador acabou de digitar.

E a mesma precedencia das outras correcoes deste fluxo: o projeto manda quando
existe, e a escolha ad-hoc vale quando nao ha projeto para mandar.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.core.recording.live_analysis_post_processor import (
    LiveAnalysisPostProcessorMixin,
)
from zebtrack.settings import load_settings


def _pristine():
    """Settings do ``config.yaml``, sem o override local da maquina."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    return load_settings(
        default_config_path=root / "config.yaml",
        override_config_path=root / "__ausente__.yaml",
    )


def _processor(*, has_project: bool, project_data: dict | None = None):
    """Pos-processador com um ``Settings`` compartilhado JA poluido.

    A poluicao imita o que ``LiveAnalysisDialog.apply()`` faz de verdade: escreve
    os limiares da execucao no objeto compartilhado e nao restaura.
    """
    processor = object.__new__(LiveAnalysisPostProcessorMixin)

    shared = _pristine()
    shared.video_processing.freezing_velocity_threshold = 9.0
    shared.trajectory_smoothing.window_length = 15

    processor.settings = shared
    processor.settings_baseline = _pristine()
    processor.project_manager = MagicMock()
    processor.project_manager.project_path = "/tmp/projeto" if has_project else None
    processor.project_manager.project_data = project_data if project_data is not None else {}
    return processor, shared


def test_a_project_session_ignores_the_polluted_shared_settings() -> None:
    """O caso que importa para o teste de projeto ao vivo."""
    processor, shared = _processor(has_project=True)
    baseline_value = processor.settings_baseline.video_processing.freezing_velocity_threshold

    service = processor._build_post_analysis_service()

    assert shared.video_processing.freezing_velocity_threshold == 9.0, "o fixture nao poluiu"
    assert service.settings.video_processing.freezing_velocity_threshold == baseline_value
    assert service.settings.trajectory_smoothing.window_length == (
        processor.settings_baseline.trajectory_smoothing.window_length
    )


def test_the_project_own_values_win_over_the_baseline() -> None:
    """O snapshot e ``projeto > baseline``, nao so ``baseline``."""
    processor, _shared = _processor(
        has_project=True,
        project_data={"analysis_parameters": {"freezing_vel_threshold": 2.75}},
    )

    service = processor._build_post_analysis_service()

    assert service.settings.video_processing.freezing_velocity_threshold == 2.75


def test_an_adhoc_session_keeps_what_the_operator_typed() -> None:
    """Sem projeto, o snapshot descartaria a escolha do dialogo.

    Este e o teste que impede o conserto do caso de projeto de quebrar o avulso.
    """
    processor, shared = _processor(has_project=False)

    service = processor._build_post_analysis_service()

    assert service.settings is shared
    assert service.settings.video_processing.freezing_velocity_threshold == 9.0


def test_the_shared_object_is_never_mutated() -> None:
    """Montar o servico nao pode escrever de volta no objeto compartilhado."""
    processor, shared = _processor(has_project=True)
    before = (
        shared.video_processing.freezing_velocity_threshold,
        shared.trajectory_smoothing.window_length,
    )

    processor._build_post_analysis_service()

    assert (
        shared.video_processing.freezing_velocity_threshold,
        shared.trajectory_smoothing.window_length,
    ) == before


def test_the_roi_rule_still_comes_from_the_project() -> None:
    """A regra de ROI continua resolvida pela mesma fonte de antes.

    Ela existe para casar com o que o Arduino dispara em tempo real; trocar a
    fonte aqui faria o relatorio contar uma entrada que o estimulo nao seguiu.
    """
    processor, _shared = _processor(
        has_project=True,
        project_data={"roi_settings": {"roi_inclusion_rule": "centroid_in"}},
    )

    service = processor._build_post_analysis_service()

    assert service.roi_rule is not None
    assert service.roi_rule.rule == "centroid_in"


def test_a_service_without_baseline_still_works() -> None:
    """``settings_baseline`` ausente degrada para o objeto de sessao.

    Um ``LiveCameraService`` construido a mao (testes antigos, chamadores fora do
    DI) nao pode explodir na pos-analise depois de a gravacao ja ter acontecido.
    """
    processor, _shared = _processor(has_project=True)
    del processor.settings_baseline

    service = processor._build_post_analysis_service()

    assert service is not None
