"""Excel summary export.

Exports the tidy analysis DataFrame to ``.xlsx`` or ``.csv`` with
display-friendly column names and geotaxis renaming.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd
import structlog

if TYPE_CHECKING:
    from zebtrack.analysis.reporters.reporter_context import ReporterContext

log = structlog.get_logger(__name__)

# Nome default do pandas para a primeira aba. Mantido explicitamente porque
# scripts de terceiros leem este arquivo por POSIÇÃO/nome de aba: a segunda aba
# é aditiva, a primeira não pode mudar de identidade.
MAIN_SHEET_NAME = "Sheet1"
PER_ANIMAL_SHEET_NAME = "por_animal"


class ExcelReporter:
    """Export summary data in Excel or CSV format.

    Example:
        >>> ctx = ReporterContext.from_analysis(analysis_result)
        >>> ExcelReporter(ctx).export_summary("summary.xlsx")
    """

    def __init__(self, ctx: ReporterContext) -> None:
        self._ctx = ctx

    def export_summary(
        self,
        output_path: Path | str,
        expected_roi_names: list[str] | None = None,
    ) -> None:
        """Export summary data to Excel or CSV.

        The output applies display-friendly column names (via
        ``DISPLAY_COLUMN_MAPPING``) and geotaxis renaming when applicable.

        Args:
            output_path: Output file path (``.xlsx`` or ``.csv``).
            expected_roi_names: Optional list of ROI names for schema
                standardisation.  Missing ROI columns are added with
                ``NaN`` / ``0`` defaults.
        """
        path = Path(output_path) if isinstance(output_path, str) else output_path
        path.parent.mkdir(parents=True, exist_ok=True)

        data_to_export = self._ctx.tidy_data
        if expected_roi_names:
            data_to_export = self._ctx.data_transformer.standardize_roi_columns(
                data_to_export, expected_roi_names
            )

        self._ctx.data_transformer.validate_schema(data_to_export)

        # Geotaxis column renaming -----------------------------------------
        height_cm = float((self._ctx.metadata or {}).get("aquarium_height_cm", 0) or 0)
        num_zones = int((self._ctx.metadata or {}).get("geotaxis_num_zones", 0) or 0)
        if num_zones == 0 and hasattr(self._ctx, "behavioral_config"):
            num_zones = int(self._ctx.behavioral_config.get("geotaxis_num_zones", 0) or 0)

        # Apply display formatting
        data_to_export = self._ctx.data_transformer.prepare_for_display(
            data_to_export, height_cm, num_zones
        )

        fmt = "csv" if str(path).lower().endswith(".csv") else "excel"
        per_animal = self._per_animal_frame()
        if fmt == "excel":
            if per_animal is None:
                # ``sheet_name`` explícito nos DOIS ramos: o nome da aba
                # principal é contrato com quem lê o arquivo, não pode depender
                # de um default futuro do pandas.
                data_to_export.to_excel(
                    path, sheet_name=MAIN_SHEET_NAME, index=False, engine="openpyxl"
                )
            else:
                with pd.ExcelWriter(path, engine="openpyxl") as writer:
                    data_to_export.to_excel(writer, sheet_name=MAIN_SHEET_NAME, index=False)
                    per_animal.to_excel(writer, sheet_name=PER_ANIMAL_SHEET_NAME, index=False)
        else:
            data_to_export.to_csv(path, index=False)

        log.info(
            "reporter.excel.exported",
            path=str(path),
            format=fmt,
            per_animal_rows=0 if per_animal is None else len(per_animal),
        )

    def _per_animal_frame(self) -> pd.DataFrame | None:
        """Tabela longa por animal, ou ``None`` quando não há o que escrever.

        Uma aba vazia é pior do que aba nenhuma: o pesquisador abre, vê só
        cabeçalho e não sabe se a análise falhou ou se não havia dado.
        """
        per_animal = getattr(self._ctx, "per_animal_data", None)
        if per_animal is None or per_animal.empty:
            return None
        return per_animal
