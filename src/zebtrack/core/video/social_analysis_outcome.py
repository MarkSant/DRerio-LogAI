"""Resultado tipado da análise de proximidade social.

Substitui o antigo ``dict | None`` ambíguo devolvido por
``AnalysisPipelineRunnerMixin._analyze_social_proximity``: agora toda ausência
da seção social no relatório carrega um motivo explícito, e todo motivo — exceto
``disabled``, que é escolha deliberada do pesquisador — vira um aviso visível em
``validation_warnings``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, get_args

SocialSkipReason = Literal[
    "disabled",
    "malformed_config",
    "no_calibration",
    "no_track_id_column",
    "single_track",
    "failed",
]

SOCIAL_SKIP_REASONS: tuple[str, ...] = get_args(SocialSkipReason)

#: Raio default (cm) do ROI dinâmico de proximidade social.
DEFAULT_SOCIAL_RADIUS_CM = 5.0

_FALLBACK_SKIP_WARNING = "Social proximity analysis was skipped for an unspecified reason."

# Mensagens em inglês para casar com os demais avisos do apêndice de validação
# do relatório (``WordReporter._append_validation_warnings``).
_SKIP_WARNINGS: dict[str, str] = {
    "malformed_config": (
        "Social proximity analysis was skipped: the analysis profile's 'social' section is "
        "malformed, so it is unknown whether the analysis was meant to run."
    ),
    "no_calibration": (
        "Social proximity analysis was skipped: this video has no pixel/cm calibration, "
        "so the proximity radius cannot be converted to pixels."
    ),
    "no_track_id_column": (
        "Social proximity analysis was skipped: the trajectory has no 'track_id' column, "
        "so individuals cannot be told apart."
    ),
    "single_track": (
        "Social proximity analysis was skipped: fewer than two tracks were available "
        "after filtering, and proximity requires at least two animals."
    ),
    "failed": "Social proximity analysis failed and was omitted from this report.",
}


@dataclass(frozen=True)
class SocialAnalysisOutcome:
    """Resultado da análise social: os dados OU o motivo explícito da ausência.

    Attributes:
        result: Métricas sociais quando a análise rodou; ``None`` quando pulada.
        skipped_reason: Motivo da ausência; ``None`` quando a análise rodou.
        detail: Contexto extra (ex.: mensagem da exceção no motivo ``failed``).
        notes: Avisos de degradação de uma análise que RODOU (ex.: raio caiu no
            default por não ser conversível). Também visíveis no relatório.
    """

    result: dict[str, Any] | None = None
    skipped_reason: SocialSkipReason | None = None
    detail: str | None = None
    notes: tuple[str, ...] = ()

    @classmethod
    def success(
        cls,
        result: dict[str, Any],
        notes: tuple[str, ...] = (),
    ) -> SocialAnalysisOutcome:
        """Cria um resultado bem-sucedido, com eventuais notas de degradação."""
        return cls(result=result, notes=notes)

    @classmethod
    def skipped(
        cls,
        reason: SocialSkipReason,
        detail: str | None = None,
        notes: tuple[str, ...] = (),
    ) -> SocialAnalysisOutcome:
        """Cria um resultado pulado com motivo explícito."""
        return cls(result=None, skipped_reason=reason, detail=detail, notes=notes)

    @property
    def succeeded(self) -> bool:
        """True quando a análise social realmente produziu métricas."""
        return self.skipped_reason is None

    @property
    def warning_message(self) -> str | None:
        """Aviso do motivo do skip, destinado ao relatório.

        Returns:
            A mensagem do motivo, ou ``None`` quando não há motivo a avisar —
            sucesso ou ``disabled`` (o usuário desligou a análise de propósito).
        """
        if self.skipped_reason is None or self.skipped_reason == "disabled":
            return None

        # `.get` defensivo: um motivo novo sem mensagem não pode levantar
        # KeyError no meio da geração do relatório.
        base = _SKIP_WARNINGS.get(self.skipped_reason, _FALLBACK_SKIP_WARNING)
        if self.detail:
            return f"{base} ({self.detail})"
        return base

    @property
    def warning_messages(self) -> list[str]:
        """Todos os avisos a propagar para ``validation_warnings``.

        Inclui as notas de degradação (análise rodou, mas com ressalva) e, se
        houver, a mensagem do motivo do skip.
        """
        messages = list(self.notes)
        skip_message = self.warning_message
        if skip_message is not None:
            messages.append(skip_message)
        return messages
