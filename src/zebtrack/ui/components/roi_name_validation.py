"""Validação do nome de uma ROI, no ponto em que o operador o digita.

O nome de uma ROI não é rótulo cosmético: ele vira o nome da coluna
``in_<nome>_stable`` no DataFrame da análise e a chave dos dicionários de
métricas em :mod:`zebtrack.analysis.roi` — tempo, latência, entradas, saídas,
distância. A aba ``por_animal`` do ``.xlsx`` é indexada por
*experimento × track_id × roi*.

Duas ROIs com o mesmo nome produzem a mesma coluna e a mesma chave: a segunda
sobrescreve a primeira e **uma das duas regiões desaparece do relatório**, sem
aviso. O polígono continua desenhado na tela, então nada indica a perda — ela
só aparece no relatório agregado, quando a sessão já acabou.

Dois detalhes que o ``if not roi_name`` do call site deixava passar:

* ``"   "`` é verdadeiro em Python, então um nome só de espaços era aceito e
  gerava uma coluna de cabeçalho em branco na planilha;
* o renomear localizava a ROI por ``roi_names.index(old_name)``, que devolve a
  PRIMEIRA ocorrência — havendo homônimas, renomeava a errada.
"""

from __future__ import annotations

from collections.abc import Iterable

from zebtrack.i18n import _


class RoiNameError(ValueError):
    """Nome de ROI recusado. A mensagem é voltada ao operador."""


def normalize_roi_name(raw: str | None) -> str:
    """Nome sem espaços nas pontas, como será gravado."""
    return (raw or "").strip()


def validate_roi_name(
    raw: str | None,
    existing_names: Iterable[str],
    *,
    current_name: str | None = None,
) -> str:
    """Devolve o nome normalizado, ou levanta :class:`RoiNameError`.

    Args:
        raw: O texto digitado pelo operador.
        existing_names: Nomes já usados no contexto (aquário/vídeo ativo).
        current_name: Ao renomear, o nome atual da própria ROI — ele não conta
            como colisão consigo mesmo.

    Raises:
        RoiNameError: Nome vazio (inclusive só espaços) ou já usado.
    """
    name = normalize_roi_name(raw)
    if not name:
        raise RoiNameError(_("The ROI name cannot be empty."))

    taken = {normalize_roi_name(existing) for existing in existing_names}
    if current_name is not None:
        taken.discard(normalize_roi_name(current_name))

    if name in taken:
        raise RoiNameError(
            _(
                "There is already an ROI called '{name}'. Two ROIs with the same "
                "name collide in the report and one of them disappears from it."
            ).format(name=name)
        )

    return name
