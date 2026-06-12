"""Testes unitários para ``ParquetSummaryReporter``.

Garante que o resumo é exportado em Parquet preservando nomes internos de
coluna, que a padronização de ROIs é aplicada quando solicitada e que o schema
é validado antes da escrita.
"""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from zebtrack.analysis.reporters import ParquetSummaryReporter


@pytest.mark.unit
class TestParquetSummaryReporter:
    """Exportação de resumo em formato Parquet."""

    def test_export_writes_readable_parquet(self, reporter_ctx, tmp_path):
        """Grava .parquet legível via pandas, com pelo menos uma linha."""
        output = tmp_path / "summary.parquet"

        ParquetSummaryReporter(reporter_ctx).export_summary(output)

        assert output.exists()
        df = pd.read_parquet(output)
        assert not df.empty

    def test_preserves_internal_column_names(self, reporter_ctx, tmp_path):
        """Parquet não aplica renomeação de exibição (schema interno estável)."""
        output = tmp_path / "internal.parquet"

        ParquetSummaryReporter(reporter_ctx).export_summary(output)

        df = pd.read_parquet(output)
        # As colunas devem coincidir com tidy_data (sem display mapping).
        assert list(df.columns) == list(reporter_ctx.tidy_data.columns)

    def test_creates_parent_directory(self, reporter_ctx, tmp_path):
        """Diretório pai inexistente é criado automaticamente."""
        output = tmp_path / "nested" / "deep" / "summary.parquet"

        ParquetSummaryReporter(reporter_ctx).export_summary(output)

        assert output.exists()

    def test_expected_roi_names_triggers_standardization(self, reporter_ctx, tmp_path):
        """expected_roi_names aciona standardize_roi_columns."""
        output = tmp_path / "std.parquet"

        with patch.object(
            reporter_ctx.data_transformer,
            "standardize_roi_columns",
            wraps=reporter_ctx.data_transformer.standardize_roi_columns,
        ) as spy:
            ParquetSummaryReporter(reporter_ctx).export_summary(
                output, expected_roi_names=["ROI1", "ROI2", "ROI_EXTRA"]
            )

        spy.assert_called_once()
        assert output.exists()

    def test_validate_schema_is_invoked(self, reporter_ctx, tmp_path):
        """validate_schema é chamado e sua falha propaga (nada é escrito)."""
        output = tmp_path / "invalid.parquet"

        with patch.object(
            reporter_ctx.data_transformer,
            "validate_schema",
            side_effect=ValueError("missing columns"),
        ):
            with pytest.raises(ValueError, match="missing columns"):
                ParquetSummaryReporter(reporter_ctx).export_summary(output)

        assert not output.exists()

    def test_string_path_accepted(self, reporter_ctx, tmp_path):
        """Aceita caminho como str."""
        output = str(tmp_path / "as_string.parquet")

        ParquetSummaryReporter(reporter_ctx).export_summary(output)

        assert (tmp_path / "as_string.parquet").exists()
