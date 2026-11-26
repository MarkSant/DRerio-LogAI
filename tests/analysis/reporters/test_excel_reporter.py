"""Testes unitários para ``ExcelReporter``.

Cobre exportação .xlsx e .csv, criação de diretório pai, validação de schema e
o caminho de renomeação geotaxia (metadados vs. behavioral_config).
"""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from zebtrack.analysis.reporters import ExcelReporter


@pytest.mark.unit
class TestExcelReporter:
    """Exportação de resumo em Excel/CSV."""

    def test_export_xlsx_is_readable(self, reporter_ctx, tmp_path):
        """Gera .xlsx legível via pandas/openpyxl."""
        output = tmp_path / "summary.xlsx"

        ExcelReporter(reporter_ctx).export_summary(output)

        assert output.exists()
        df = pd.read_excel(output)
        assert not df.empty

    def test_export_csv_branch(self, reporter_ctx, tmp_path):
        """Caminho .csv grava CSV legível sem engine Excel."""
        output = tmp_path / "summary.csv"

        with patch.object(pd.DataFrame, "to_excel") as mock_excel:
            ExcelReporter(reporter_ctx).export_summary(output)

        mock_excel.assert_not_called()
        assert output.exists()
        df = pd.read_csv(output)
        assert not df.empty

    def test_creates_parent_directory(self, reporter_ctx, tmp_path):
        """Diretório pai inexistente é criado."""
        output = tmp_path / "nested" / "summary.xlsx"

        ExcelReporter(reporter_ctx).export_summary(output)

        assert output.exists()

    def test_validate_schema_is_invoked(self, reporter_ctx, tmp_path):
        """validate_schema é chamado e sua falha propaga."""
        output = tmp_path / "invalid.xlsx"

        with patch.object(
            reporter_ctx.data_transformer,
            "validate_schema",
            side_effect=ValueError("missing columns"),
        ):
            with pytest.raises(ValueError, match="missing columns"):
                ExcelReporter(reporter_ctx).export_summary(output)

    def test_geotaxis_uses_metadata_values(self, reporter_ctx, tmp_path):
        """Metadados com aquarium_height_cm + geotaxis_num_zones alimentam prepare_for_display."""
        reporter_ctx.metadata = {
            "experiment_id": "geo",
            "aquarium_height_cm": 12.0,
            "geotaxis_num_zones": 3,
        }
        output = tmp_path / "geo.xlsx"

        with patch.object(
            reporter_ctx.data_transformer,
            "prepare_for_display",
            wraps=reporter_ctx.data_transformer.prepare_for_display,
        ) as spy:
            ExcelReporter(reporter_ctx).export_summary(output)

        spy.assert_called_once()
        args = spy.call_args.args
        assert args[1] == 12.0  # height_cm
        assert args[2] == 3  # num_zones

    def test_geotaxis_num_zones_fallback_to_behavioral_config(self, reporter_ctx, tmp_path):
        """num_zones=0 nos metadados -> fallback para behavioral_config."""
        reporter_ctx.metadata = {"experiment_id": "geo", "geotaxis_num_zones": 0}
        reporter_ctx.behavioral_config = {"geotaxis_num_zones": 4}
        output = tmp_path / "geo_fallback.xlsx"

        with patch.object(
            reporter_ctx.data_transformer,
            "prepare_for_display",
            wraps=reporter_ctx.data_transformer.prepare_for_display,
        ) as spy:
            ExcelReporter(reporter_ctx).export_summary(output)

        assert spy.call_args.args[2] == 4

    def test_expected_roi_names_triggers_standardization(self, reporter_ctx, tmp_path):
        """expected_roi_names aciona standardize_roi_columns."""
        output = tmp_path / "std.xlsx"

        with patch.object(
            reporter_ctx.data_transformer,
            "standardize_roi_columns",
            wraps=reporter_ctx.data_transformer.standardize_roi_columns,
        ) as spy:
            ExcelReporter(reporter_ctx).export_summary(
                output, expected_roi_names=["ROI1", "ROI2", "ROI_EXTRA"]
            )

        spy.assert_called_once()


class TestAquariumColumnHeaderFollowsTheAnimalModel:
    """Barnes v8.1 stage 3: the ``aquarium_id`` column reads "Arena" for a rodent run."""

    @staticmethod
    def _headers(ctx, tmp_path, animal):
        ctx.tidy_data = ctx.tidy_data.assign(aquarium_id=0)
        ctx.behavioral_config = {"animal_model": animal} if animal else {}
        output = tmp_path / f"{animal or 'legacy'}.xlsx"
        ExcelReporter(ctx).export_summary(output)
        return list(pd.read_excel(output).columns)

    def test_legacy_and_zebrafish_keep_the_aquarium_header(self, reporter_ctx, tmp_path):
        assert "Aquarium" in self._headers(reporter_ctx, tmp_path, None)
        assert "Aquarium" in self._headers(reporter_ctx, tmp_path, "zebrafish")

    def test_a_rodent_run_reads_arena_and_loses_nothing_else(self, reporter_ctx, tmp_path):
        legacy = self._headers(reporter_ctx, tmp_path, None)
        rodent = self._headers(reporter_ctx, tmp_path, "rodent")

        assert "Arena" in rodent and "Aquarium" not in rodent
        assert [h for h in rodent if h != "Arena"] == [h for h in legacy if h != "Aquarium"]
