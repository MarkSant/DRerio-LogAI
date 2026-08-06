"""Testes da visibilidade da análise de proximidade social.

Garante que a ausência da seção social no relatório SEMPRE tem um motivo
explícito (``SocialAnalysisOutcome.skipped_reason``) e que esse motivo — exceto
``disabled``, escolha deliberada do usuário — chega aos ``validation_warnings``
do relatório sem abortar a análise geral.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest

from zebtrack.analysis.roi import ROIAnalyzer
from zebtrack.core.video.analysis_pipeline_runner import AnalysisPipelineRunnerMixin
from zebtrack.core.video.social_analysis_outcome import (
    DEFAULT_SOCIAL_RADIUS_CM,
    SOCIAL_SKIP_REASONS,
    SocialAnalysisOutcome,
)


def _make_settings():
    """Settings mínimo com os campos lidos pelo mixin."""
    return SimpleNamespace(
        video_processing=SimpleNamespace(
            sharp_turn_threshold_deg_s=90.0,
            freezing_velocity_threshold=1.5,
            freezing_min_duration_s=1.0,
            fps=30.0,
        ),
        trajectory_smoothing=SimpleNamespace(window_length=5, polyorder=2),
    )


@pytest.fixture
def runner():
    """Instância do mixin com atributos injetados (sem threads/IO)."""
    instance = AnalysisPipelineRunnerMixin()
    instance.settings = _make_settings()
    instance.project_manager = Mock()
    instance.ui_event_bus = Mock()
    return instance


@pytest.fixture
def two_track_df():
    """Duas trajetórias próximas o bastante para formarem um grupo social."""
    return pd.DataFrame(
        {
            "frame": [0, 0, 1, 1, 2, 2],
            "track_id": [1, 2, 1, 2, 1, 2],
            "x_center_px": [100.0, 105.0, 101.0, 106.0, 102.0, 107.0],
            "y_center_px": [100.0, 100.0, 101.0, 101.0, 102.0, 102.0],
        }
    )


def _ctx_stub(warnings: list[str] | None = None) -> SimpleNamespace:
    """ReporterContext mínimo: só o que ``_record_social_outcome_warning`` toca."""
    avisos: list[str] = [] if warnings is None else warnings
    return SimpleNamespace(
        validation_warnings=avisos,
        report={"validacao": {"avisos": avisos}},
    )


def _run(runner, df, profile, *, pixelcm=(10.0, 10.0)) -> SocialAnalysisOutcome:
    return runner._analyze_social_proximity(
        filtered_df=df,
        analysis_profile=profile,
        pixelcm_x=pixelcm[0],
        pixelcm_y=pixelcm[1],
        experiment_id="exp_social",
    )


@pytest.mark.unit
class TestSkipReasons:
    """Um caso por motivo de skip — nenhum ``None`` mudo sobra."""

    def test_disabled(self, runner, two_track_df):
        outcome = _run(runner, two_track_df, {"social": {"enabled": False}})

        assert outcome.result is None
        assert outcome.skipped_reason == "disabled"
        # Escolha do usuário: NÃO vira aviso no relatório.
        assert outcome.warning_message is None

    def test_missing_profile_is_disabled(self, runner, two_track_df):
        outcome = _run(runner, two_track_df, None)

        assert outcome.skipped_reason == "disabled"
        assert outcome.warning_message is None

    @pytest.mark.parametrize(
        "profile",
        [
            {"social": True},
            {"social": "enabled"},
            {"social": [1, 2]},
            "perfil legado em string",
            42,
        ],
    )
    def test_malformed_config_is_not_confused_with_disabled(self, runner, two_track_df, profile):
        """Config quebrada NÃO pode se passar por 'o usuário desligou'."""
        outcome = _run(runner, two_track_df, profile)

        assert outcome.result is None
        assert outcome.skipped_reason == "malformed_config"
        assert "malformed" in (outcome.warning_message or "")

    def test_no_calibration(self, runner, two_track_df):
        outcome = _run(
            runner,
            two_track_df,
            {"social": {"enabled": True}},
            pixelcm=(None, None),
        )

        assert outcome.result is None
        assert outcome.skipped_reason == "no_calibration"
        assert "calibration" in (outcome.warning_message or "")

    def test_no_track_id_column(self, runner):
        df = pd.DataFrame({"frame": [0, 1], "x_center_px": [1.0, 2.0]})

        outcome = _run(runner, df, {"social": {"enabled": True}})

        assert outcome.result is None
        assert outcome.skipped_reason == "no_track_id_column"
        assert "track_id" in (outcome.warning_message or "")

    def test_single_track(self, runner):
        df = pd.DataFrame({"frame": [0, 1, 2], "track_id": [1, 1, 1]})

        outcome = _run(runner, df, {"social": {"enabled": True}})

        assert outcome.result is None
        assert outcome.skipped_reason == "single_track"
        message = outcome.warning_message or ""
        assert "at least two" in message
        assert "1 track(s) available" in message

    def test_failed_carries_exception_message(self, runner, two_track_df, monkeypatch):
        def _boom(*_args, **_kwargs):
            raise ValueError("coluna x_center_px ausente")

        monkeypatch.setattr(ROIAnalyzer, "analyze_social_proximity", staticmethod(_boom))

        outcome = _run(runner, two_track_df, {"social": {"enabled": True}})

        assert outcome.result is None
        assert outcome.skipped_reason == "failed"
        assert "coluna x_center_px ausente" in (outcome.warning_message or "")

    def test_unexpected_exception_is_contained(self, runner, two_track_df, monkeypatch):
        """Exceção fora do conjunto esperado também vira `failed`, não propaga."""

        def _boom(*_args, **_kwargs):
            raise RuntimeError("falha geométrica inesperada")

        monkeypatch.setattr(ROIAnalyzer, "analyze_social_proximity", staticmethod(_boom))

        outcome = _run(runner, two_track_df, {"social": {"enabled": True}})

        assert outcome.skipped_reason == "failed"
        assert "falha geométrica inesperada" in (outcome.warning_message or "")

    def test_every_declared_reason_is_reachable_and_typed(self):
        """Todo motivo declarado tem mensagem, menos `disabled` (silencioso)."""
        for reason in SOCIAL_SKIP_REASONS:
            outcome = SocialAnalysisOutcome.skipped(reason)  # type: ignore[arg-type]
            assert outcome.succeeded is False
            if reason == "disabled":
                assert outcome.warning_message is None
            else:
                assert outcome.warning_message


@pytest.mark.unit
class TestHappyPath:
    def test_two_close_tracks_produce_social_metrics(self, runner, two_track_df):
        outcome = _run(
            runner,
            two_track_df,
            {"social": {"enabled": True, "radius_cm": 5.0}},
        )

        assert outcome.skipped_reason is None
        assert outcome.succeeded is True
        assert outcome.warning_message is None
        assert outcome.result is not None
        assert outcome.result["social_time_seconds"]
        assert outcome.result["social_time_percentage"]

    def test_invalid_radius_falls_back_to_default_but_says_so(
        self, runner, two_track_df, monkeypatch
    ):
        """Cair no raio default não pode ser silencioso: o raio define o contato."""
        captured: dict[str, float] = {}

        def _capture(_df, radius_cm, _px, _py):
            captured["radius_cm"] = radius_cm
            return {"social_time_seconds": {}, "social_time_percentage": {}}

        monkeypatch.setattr(ROIAnalyzer, "analyze_social_proximity", staticmethod(_capture))

        outcome = _run(
            runner,
            two_track_df,
            {"social": {"enabled": True, "radius_cm": "não é número"}},
        )

        assert outcome.succeeded is True
        assert captured["radius_cm"] == DEFAULT_SOCIAL_RADIUS_CM
        # A degradação vira aviso visível, mesmo com a análise bem-sucedida.
        assert len(outcome.notes) == 1
        assert "não é número" in outcome.notes[0]
        assert outcome.warning_messages == list(outcome.notes)

    def test_valid_radius_produces_no_notes(self, runner, two_track_df, monkeypatch):
        captured: dict[str, float] = {}

        def _capture(_df, radius_cm, _px, _py):
            captured["radius_cm"] = radius_cm
            return {"social_time_seconds": {}, "social_time_percentage": {}}

        monkeypatch.setattr(ROIAnalyzer, "analyze_social_proximity", staticmethod(_capture))

        outcome = _run(runner, two_track_df, {"social": {"enabled": True, "radius_cm": 3.5}})

        assert captured["radius_cm"] == 3.5
        assert outcome.notes == ()
        assert outcome.warning_messages == []


@pytest.mark.unit
class TestWarningPropagation:
    """O motivo precisa chegar ao relatório, não só ao log."""

    @pytest.mark.parametrize(
        "reason",
        [
            "malformed_config",
            "no_calibration",
            "no_track_id_column",
            "single_track",
            "failed",
        ],
    )
    def test_reason_reaches_report_warnings(self, runner, reason):
        ctx = _ctx_stub()
        outcome = SocialAnalysisOutcome.skipped(reason, detail="detalhe")  # type: ignore[arg-type]

        runner._record_social_outcome_warning(ctx=ctx, outcome=outcome)

        assert len(ctx.validation_warnings) == 1
        assert "detalhe" in ctx.validation_warnings[0]
        # A lista do ctx e a do dicionário do relatório permanecem coerentes.
        assert ctx.report["validacao"]["avisos"] == ctx.validation_warnings

    def test_disabled_adds_no_warning(self, runner):
        ctx = _ctx_stub()

        runner._record_social_outcome_warning(
            ctx=ctx, outcome=SocialAnalysisOutcome.skipped("disabled")
        )

        assert ctx.validation_warnings == []

    def test_success_adds_no_warning(self, runner):
        ctx = _ctx_stub()

        runner._record_social_outcome_warning(
            ctx=ctx,
            outcome=SocialAnalysisOutcome.success({"social_time_seconds": {}}),
        )

        assert ctx.validation_warnings == []

    def test_existing_warnings_are_preserved(self, runner):
        ctx = _ctx_stub(["aviso preexistente"])

        runner._record_social_outcome_warning(
            ctx=ctx, outcome=SocialAnalysisOutcome.skipped("single_track")
        )

        assert ctx.validation_warnings[0] == "aviso preexistente"
        assert len(ctx.validation_warnings) == 2

    def test_context_without_warning_list_is_repaired(self, runner):
        ctx = SimpleNamespace(validation_warnings=None, report=None)

        runner._record_social_outcome_warning(
            ctx=ctx, outcome=SocialAnalysisOutcome.skipped("failed", detail="erro X")
        )

        assert isinstance(ctx.validation_warnings, list)
        assert "erro X" in ctx.validation_warnings[0]

    def test_degradation_note_reaches_report_even_on_success(self, runner):
        ctx = _ctx_stub()
        outcome = SocialAnalysisOutcome.success(
            {"social_time_seconds": {}}, notes=("raio caiu no default",)
        )

        runner._record_social_outcome_warning(ctx=ctx, outcome=outcome)

        assert ctx.validation_warnings == ["raio caiu no default"]
        assert ctx.report["validacao"]["avisos"] == ["raio caiu no default"]

    def test_malformed_report_section_does_not_raise(self, runner):
        """Relatório com estrutura inesperada não pode derrubar a análise."""
        ctx = SimpleNamespace(validation_warnings=[], report={"validacao": "não é dict"})

        runner._record_social_outcome_warning(
            ctx=ctx, outcome=SocialAnalysisOutcome.skipped("single_track")
        )

        # O aviso ainda chega ao ctx, que é o que o WordReporter lê.
        assert len(ctx.validation_warnings) == 1


@pytest.mark.unit
class TestNeverRaises:
    """A proximidade social é opcional: não pode derrubar o pipeline inteiro."""

    def test_broken_track_id_column_does_not_propagate(self, runner):
        # Coluna 'track_id' duplicada faz df["track_id"] devolver um DataFrame,
        # cujo .dropna() não tem .unique() → AttributeError nos pré-checks.
        df = pd.DataFrame(
            [[0, 1, 1], [1, 1, 2]],
            columns=["frame", "track_id", "track_id"],
        )

        outcome = _run(runner, df, {"social": {"enabled": True}})

        assert outcome.skipped_reason == "failed"
        assert outcome.warning_message

    def test_exception_inside_config_resolution_is_contained(self, runner, monkeypatch):
        def _boom(**_kwargs):
            raise RuntimeError("perfil ilegível")

        monkeypatch.setattr(runner, "_resolve_social_config", _boom)

        outcome = _run(runner, pd.DataFrame(), {"social": {"enabled": True}})

        assert outcome.skipped_reason == "failed"
        assert "perfil ilegível" in (outcome.warning_message or "")


@pytest.mark.unit
class TestNetworkxIsAHardDependency:
    def test_roi_module_imports_networkx_at_top_level(self):
        """networkx é dependência dura — sem degradação silenciosa."""
        import zebtrack.analysis.roi as roi_module

        assert roi_module.nx is not None
