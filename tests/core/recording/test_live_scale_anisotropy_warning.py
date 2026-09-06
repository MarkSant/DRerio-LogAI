"""Escala calibrada, mas errada: os dois eixos discordando.

O caso
------
As dimensões reais do aquário existiam como variáveis no ``LiveAnalysisDialog``,
eram validadas e chegavam ao ``analysis_config`` — mas **nenhum widget as
expunha**. Ficavam travadas no default 10,0 x 10,0 cm.

Numa sessão real (2026-09-06), um labirinto de proporção ~1,63 declarado como
quadrado produziu **95,8 px/cm** no eixo X contra **60,1** no Y. O relatório saiu
com números plausíveis e errados.

Por que um aviso, e não uma recusa
----------------------------------
Só o operador sabe a geometria do aparato. Uma câmera bem inclinada ou uma lente
com distorção forte podem legitimamente dar eixos diferentes, e recusar a
análise depois de a gravação já ter acontecido destruiria dado que não volta.
O aviso vai para ``validation_warnings``, que é o MESMO objeto que
``report["validacao"]["avisos"]`` — sai carimbado no ``.docx``, não só num log.

O erro é ANISOTRÓPICO, e é isso que o torna grave: um deslocamento horizontal e
um vertical do mesmo tamanho real viram valores diferentes, então nenhuma
constante aplicada depois conserta o relatório.
"""

from __future__ import annotations

import pytest

from zebtrack.core.recording.live_analysis_post_processor import (
    LiveAnalysisPostProcessorMixin,
)


def _warn(pixelcm_x: float, pixelcm_y: float) -> list[str]:
    """Roda o aviso REAL do mixin e devolve a lista de avisos.

    ``object.__new__`` porque o mixin so existe dentro de ``LiveCameraService``,
    cuja construcao exige camera, detector e event bus. O metodo exercitado e o
    de producao, e ele so le uma constante de classe.
    """
    processor = object.__new__(LiveAnalysisPostProcessorMixin)
    warnings: list[str] = []
    processor._warn_if_scale_is_anisotropic(warnings, pixelcm_x, pixelcm_y)
    return warnings


def test_the_measured_session_is_flagged() -> None:
    """O caso real: 95,8 contra 60,1 px/cm."""
    warnings = _warn(95.8, 60.1)

    assert len(warnings) == 1
    assert "95.8" in warnings[0] and "60.1" in warnings[0]


def test_a_uniform_scale_is_silent() -> None:
    """Escala coerente não pode gerar ruído.

    Um aviso que aparece em toda sessão é um aviso que o pesquisador aprende a
    ignorar — inclusive na sessão em que ele importa.
    """
    assert _warn(96.0, 96.0) == []
    assert _warn(96.0, 95.0) == []


def test_small_differences_stay_silent() -> None:
    """Inclinação leve e distorção de lente produzem poucos por cento."""
    assert _warn(100.0, 90.0) == []  # 11%
    assert _warn(100.0, 82.0) == []  # 22%, ainda sob o limiar de 25%


def test_the_threshold_is_where_it_says_it_is() -> None:
    """A fronteira declarada é a fronteira aplicada."""
    limit = LiveAnalysisPostProcessorMixin.MAX_PLAUSIBLE_SCALE_ANISOTROPY

    assert _warn(100.0, 100.0 / limit) == []
    assert _warn(100.0, 100.0 / (limit + 0.01)) != []


def test_the_warning_is_symmetric() -> None:
    """Qual eixo é o maior não muda o diagnóstico."""
    assert len(_warn(60.1, 95.8)) == 1
    assert len(_warn(95.8, 60.1)) == 1


@pytest.mark.parametrize(("px_x", "px_y"), [(0.0, 50.0), (50.0, 0.0), (-1.0, 50.0)])
def test_degenerate_values_do_not_raise(px_x: float, px_y: float) -> None:
    """Zero ou negativo é "escala desconhecida", tratada pelo outro aviso.

    Dividir aqui explodiria a pós-análise DEPOIS de a gravação ter acontecido —
    e perder a análise de uma sessão que já rodou é pior do que qualquer aviso
    faltando.
    """
    assert _warn(px_x, px_y) == []


def test_the_warning_says_what_to_do() -> None:
    """A mensagem precisa levar a uma ação, não só ao susto.

    Ela nomeia a causa provável (dimensões digitadas), diz por que não dá para
    corrigir depois, e diz o que fazer: medir de novo e regerar.
    """
    message = _warn(95.8, 60.1)[0].lower()

    assert "dimensions" in message
    assert "re-measure" in message
    assert "regenerate" in message
