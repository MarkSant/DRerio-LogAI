"""Abas do ``<video>_summary.xlsx``: resumo + ``por_animal``.

A aba principal é contrato com quem já lê o arquivo (nome e posição); a segunda
é aditiva e só existe quando há dado por animal — aba vazia seria pior do que
aba nenhuma.
"""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from zebtrack.analysis.data_transformer import PER_ANIMAL_COLUMNS
from zebtrack.analysis.reporters import ExcelReporter
from zebtrack.analysis.reporters.excel_reporter import (
    MAIN_SHEET_NAME,
    PER_ANIMAL_SHEET_NAME,
)


def _sheet_names(path) -> list[str]:
    """Nomes das abas do arquivo, sem depender de stubs do openpyxl."""
    with pd.ExcelFile(path) as workbook:
        return list(workbook.sheet_names)


@pytest.mark.unit
class TestExcelReporterSheets:
    """Estrutura de abas do resumo."""

    def test_two_sheets_when_per_animal_has_data(self, reporter_ctx, tmp_path):
        """Com métricas por animal o arquivo ganha a segunda aba."""
        output = tmp_path / "summary.xlsx"
        assert not reporter_ctx.per_animal_data.empty

        ExcelReporter(reporter_ctx).export_summary(output)

        assert _sheet_names(output) == [MAIN_SHEET_NAME, PER_ANIMAL_SHEET_NAME]

        per_animal = pd.read_excel(output, sheet_name=PER_ANIMAL_SHEET_NAME)
        assert list(per_animal.columns) == list(PER_ANIMAL_COLUMNS)
        assert len(per_animal) == len(reporter_ctx.per_animal_data)

    def test_single_sheet_when_there_is_no_per_animal_data(self, reporter_ctx, tmp_path):
        """Sem dado por animal, uma aba só — nenhuma aba vazia é criada."""
        output = tmp_path / "summary_empty.xlsx"
        reporter_ctx.per_animal_data = reporter_ctx.per_animal_data.iloc[0:0]

        ExcelReporter(reporter_ctx).export_summary(output)

        assert _sheet_names(output) == [MAIN_SHEET_NAME]

    def test_single_sheet_without_roi_analysis(self, reporter_ctx_no_rois, tmp_path):
        """Contexto sem ROIs: a tabela por animal nasce vazia e a aba não é escrita."""
        output = tmp_path / "summary_no_rois.xlsx"
        assert reporter_ctx_no_rois.per_animal_data.empty

        ExcelReporter(reporter_ctx_no_rois).export_summary(output)

        assert _sheet_names(output) == [MAIN_SHEET_NAME]

    def test_main_sheet_keeps_its_name_and_content(self, reporter_ctx, tmp_path):
        """A aba principal continua sendo a primeira, com o nome default do pandas."""
        with_second = tmp_path / "with.xlsx"
        without_second = tmp_path / "without.xlsx"

        ExcelReporter(reporter_ctx).export_summary(with_second)
        reporter_ctx.per_animal_data = reporter_ctx.per_animal_data.iloc[0:0]
        ExcelReporter(reporter_ctx).export_summary(without_second)

        pd.testing.assert_frame_equal(
            pd.read_excel(with_second),
            pd.read_excel(without_second),
        )
        assert _sheet_names(with_second)[0] == MAIN_SHEET_NAME

    def test_single_sheet_branch_names_the_sheet_explicitly(self, reporter_ctx, tmp_path):
        """O ramo de aba única também passa ``sheet_name``, não confia no default.

        O nome é contrato com quem lê o arquivo; depender do default do pandas
        deixaria os dois ramos livres para divergir numa versão futura.
        """
        output = tmp_path / "single.xlsx"
        reporter_ctx.per_animal_data = reporter_ctx.per_animal_data.iloc[0:0]

        with patch.object(pd.DataFrame, "to_excel") as mock_to_excel:
            ExcelReporter(reporter_ctx).export_summary(output)

        assert mock_to_excel.call_args.kwargs["sheet_name"] == MAIN_SHEET_NAME

    def test_summary_carries_unobserved_time(self, reporter_ctx, tmp_path):
        """A coluna escalar de tempo não observado chega à aba principal."""
        output = tmp_path / "unobserved.xlsx"

        ExcelReporter(reporter_ctx).export_summary(output)

        df = pd.read_excel(output)
        assert "Unobserved Time (s)" in df.columns

    def test_csv_branch_ignores_the_second_table(self, reporter_ctx, tmp_path):
        """CSV é um arquivo só: a tabela por animal não muda esse caminho."""
        output = tmp_path / "summary.csv"

        ExcelReporter(reporter_ctx).export_summary(output)

        assert output.exists()
        assert not pd.read_csv(output).empty
