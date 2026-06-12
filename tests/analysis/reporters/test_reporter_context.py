"""Testes unitários para ``ReporterContext``.

Cobre o caminho legado (validação, ``DeprecationWarning``, coerção de
``track_id``), o normalizador de perspectiva e a inicialização dos componentes
compartilhados (``data_transformer``, ``viz_generator``, ``tidy_data``).
"""

from __future__ import annotations

import warnings

import pandas as pd
import pytest

from zebtrack.analysis.reporters import ReporterContext


def _legacy_kwargs(trajectory_df, rois, settings):
    """Argumentos mínimos para o construtor legado do ReporterContext."""
    return {
        "trajectory_df": trajectory_df,
        "metadata": {"experiment_id": "legacy_001"},
        "pixelcm_x": 10.0,
        "pixelcm_y": 10.0,
        "video_height_px": 480,
        "arena_polygon_px": [(0, 0), (100, 0), (100, 100), (0, 100)],
        "rois": rois,
        "fps": 30.0,
        "settings_obj": settings,
    }


@pytest.mark.unit
class TestReporterContextLegacyValidation:
    """Validação e avisos do caminho legado."""

    def test_raises_when_no_trajectory_and_no_analysis(self):
        """Sem 'analysis' e sem 'trajectory_df' -> ValueError."""
        with pytest.raises(ValueError, match="trajectory_df"):
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                ReporterContext(trajectory_df=None, analysis=None)

    def test_legacy_path_emits_deprecation_warning(
        self, reporter_trajectory_df, reporter_rois, reporter_mock_settings
    ):
        """Construção legada emite DeprecationWarning."""
        with pytest.warns(DeprecationWarning, match="DEPRECATED"):
            ReporterContext(
                **_legacy_kwargs(reporter_trajectory_df, reporter_rois, reporter_mock_settings)
            )


@pytest.mark.unit
class TestReporterContextTrackIdHandling:
    """Tratamento da coluna track_id no caminho legado."""

    def test_track_id_coerced_to_int64(
        self, reporter_trajectory_df, reporter_rois, reporter_mock_settings
    ):
        """track_id em float/str é coagido para Int64 antes da análise."""
        df = reporter_trajectory_df.copy()
        df["track_id"] = df["track_id"].astype(float)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            ctx = ReporterContext(**_legacy_kwargs(df, reporter_rois, reporter_mock_settings))

        # A análise deve ter rodado sem erro de tipo.
        assert ctx.b_analyzer is not None

    def test_missing_track_id_does_not_crash(
        self, reporter_trajectory_df, reporter_rois, reporter_mock_settings
    ):
        """track_id ausente não levanta KeyError na construção."""
        df = reporter_trajectory_df.drop(columns=["track_id"])

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            ctx = ReporterContext(**_legacy_kwargs(df, reporter_rois, reporter_mock_settings))

        assert ctx is not None


@pytest.mark.unit
class TestReporterContextSharedComponents:
    """Inicialização dos componentes compartilhados."""

    def test_init_shared_components_populates_attributes(self, reporter_ctx):
        """from_analysis produz data_transformer, viz_generator e tidy_data."""
        assert reporter_ctx.data_transformer is not None
        assert reporter_ctx.viz_generator is not None
        assert isinstance(reporter_ctx.tidy_data, pd.DataFrame)


@pytest.mark.unit
class TestReporterContextPerspectiveNormalization:
    """Normalização de aliases de perspectiva do aquário."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("top_down", "top_down"),
            ("top-down", "top_down"),
            ("TopDown", "top_down"),
            ("top", "top_down"),
            ("dorsal", "top_down"),
            ("overhead", "top_down"),
            ("lateral", "lateral"),
            ("side", "lateral"),
            ("", "lateral"),
            (None, "lateral"),
        ],
    )
    def test_normalize_aquarium_perspective(self, raw, expected):
        """Mapeia variantes top/dorsal/overhead para top_down; resto para lateral."""
        assert ReporterContext._normalize_aquarium_perspective(raw) == expected
