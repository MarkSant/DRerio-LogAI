import io
from datetime import datetime
from pathlib import Path

import matplotlib.patches as patches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from docx import Document
from docx.shared import Inches
from scipy.ndimage import gaussian_filter


class Reporter:
    """Generates tabular and visual reports from analysis results."""

    def __init__(
        self,
        behavioral_results: dict,
        roi_results: dict,
        metadata: dict,
        tracking_data: np.ndarray = None,
    ):
        self.behavioral_results = behavioral_results
        self.roi_results = roi_results
        self.metadata = metadata
        self.tracking_data = (
            tracking_data
            if tracking_data is not None
            else self._generate_mock_tracking_data()
        )
        self.tidy_data = self._create_tidy_dataframe()

    def _flatten_roi_results(self) -> dict:
        """Flattens the nested ROI results dictionary."""
        flat_results = {}
        for roi_name, metrics in self.roi_results.items():
            for metric_name, value in metrics.items():
                clean_metric = metric_name.replace("_roi", "").replace(
                    "_s", ""
                ).replace("_n", "")
                col_name = f"{clean_metric}_roi_{roi_name}_{metric_name[-1]}"
                flat_results[col_name] = value
        return flat_results

    def _create_tidy_dataframe(self) -> pd.DataFrame:
        """Creates a "tidy data" pandas DataFrame."""
        combined_data = {
            **self.metadata,
            **self.behavioral_results,
            **self._flatten_roi_results(),
        }
        combined_data["date_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return pd.DataFrame([combined_data])

    def export_summary_data(self, output_path: str, format: str = "excel"):
        """Exports the summary data to a file."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if format == "excel":
            self.tidy_data.to_excel(
                f"{output_path}.xlsx", index=False, engine="openpyxl"
            )
        elif format == "csv":
            self.tidy_data.to_csv(f"{output_path}.csv", index=False)
        elif format == "parquet":
            self.tidy_data.to_parquet(f"{output_path}.parquet", index=False)
        else:
            raise ValueError(f"Unsupported file format: {format}")

    def _generate_mock_tracking_data(self, num_points=500):
        """Helper to generate a random walk for plotting."""
        start_pos = np.array([512, 512])
        steps = np.random.randn(num_points, 2) * 15
        path = np.cumsum(steps, axis=0) + start_pos
        return np.clip(path, 0, 1024)

    def generate_trajectory_plot(self, ax: plt.Axes = None) -> plt.Figure:
        """
        Generates a trajectory plot, drawing on an existing ax or new figure.
        """
        fig = ax.get_figure() if ax else plt.figure(figsize=(6, 6))
        ax = ax or fig.add_subplot(111)
        ax.clear()

        x, y = self.tracking_data[:, 0], self.tracking_data[:, 1]
        ax.set_facecolor("lightgray")
        ax.add_patch(
            patches.Rectangle((0, 0), 1024, 1024, fill=False, edgecolor="black", lw=2)
        )

        from matplotlib.collections import LineCollection

        points = np.array([x, y]).T.reshape(-1, 1, 2)
        segments = np.concatenate([points[:-1], points[1:]], axis=1)
        lc = LineCollection(segments, cmap="viridis", norm=plt.Normalize(0, len(x)))
        lc.set_array(np.arange(len(x)))
        ax.add_collection(lc)

        ax.set_title(f"Trajetória - {self.metadata.get('experiment_id', 'N/A')}")
        ax.set_xlim(0, 1024)
        ax.set_ylim(0, 1024)
        ax.set_aspect("equal", adjustable="box")
        return fig

    def generate_heatmap(self, ax: plt.Axes = None) -> plt.Figure:
        """Generates a heatmap, drawing on an existing ax or new figure."""
        fig = ax.get_figure() if ax else plt.figure(figsize=(6, 6))
        ax = ax or fig.add_subplot(111)
        ax.clear()

        x, y = self.tracking_data[:, 0], self.tracking_data[:, 1]
        heatmap, xedges, yedges = np.histogram2d(
            x, y, bins=50, range=[[0, 1024], [0, 1024]]
        )
        heatmap = gaussian_filter(heatmap.T, sigma=2)
        im = ax.imshow(
            heatmap,
            cmap="hot",
            origin="lower",
            extent=[xedges[0], xedges[-1], yedges[0], yedges[-1]],
        )

        ax.set_title(f"Mapa de Calor - {self.metadata.get('experiment_id', 'N/A')}")
        ax.set_xlim(0, 1024)
        ax.set_ylim(0, 1024)
        ax.set_aspect("equal", adjustable="box")
        if not any(isinstance(artist, plt.colorbar.Colorbar) for artist in fig.artists):
            fig.colorbar(im, ax=ax)
        return fig

    def export_individual_report(self, output_path: str):
        """Generates a complete report for a single experiment."""
        document = Document()
        document.add_heading(
            f"Relatório de Análise - {self.metadata.get('experiment_id', 'N/A')}",
            level=1,
        )
        document.add_heading("Metadados do Experimento", level=2)
        for key, value in self.metadata.items():
            document.add_paragraph(f"{key.replace('_', ' ').title()}: {value}")

        document.add_heading("Tabela de Resumo de Métricas", level=2)
        df = self.tidy_data.drop(
            columns=[k for k in self.metadata.keys() if k in self.tidy_data.columns]
        )
        table = document.add_table(rows=1, cols=len(df.columns))
        table.style = "Table Grid"
        for i, column_name in enumerate(df.columns):
            table.cell(0, i).text = column_name
        for _, row in df.iterrows():
            cells = table.add_row().cells
            for i, value in enumerate(row):
                cells[i].text = (
                    f"{value:.2f}" if isinstance(value, (int, float)) else str(value)
                )

        document.add_page_break()
        document.add_heading("Visualizações", level=2)
        plot_configs = [
            (self.generate_trajectory_plot, "Trajetória"),
            (self.generate_heatmap, "Mapa de Calor"),
        ]
        for plot_func, name in plot_configs:
            fig = plot_func()
            with io.BytesIO() as memfile:
                fig.savefig(memfile, format="png", dpi=300)
                memfile.seek(0)
                document.add_paragraph(f"Gráfico de {name}:")
                document.add_picture(memfile, width=Inches(6.0))
            plt.close(fig)

        file_path = f"{output_path}.docx"
        document.save(file_path)
        print(f"Relatório individual salvo em: {file_path}")

    @staticmethod
    def _generate_comparative_boxplot(
        df: pd.DataFrame, metric: str, title: str
    ) -> plt.Figure:
        """Generates a comparative boxplot for a given metric."""
        fig, ax = plt.subplots(figsize=(8, 6))
        sns.boxplot(x="group_id", y=metric, data=df, ax=ax)
        sns.stripplot(x="group_id", y=metric, data=df, ax=ax, color=".25", size=6)
        ax.set_title(title, fontsize=16)
        ax.set_xlabel("Grupo Experimental", fontsize=12)
        ax.set_ylabel(metric.replace("_", " ").title(), fontsize=12)
        plt.tight_layout()
        return fig

    @staticmethod
    def export_project_report(aggregated_df: pd.DataFrame, output_path: str):
        """Generates an aggregated report for a batch project."""
        document = Document()
        document.add_heading("Relatório Agregado do Projeto", level=1)
        document.add_heading("Estatísticas Descritivas por Grupo", level=2)
        desc_stats = aggregated_df.groupby("group_id")["distancia_total_cm"].agg(
            ["mean", "std", "count"]
        )
        document.add_paragraph(
            "Estatísticas para a Distância Total Percorrida (cm):"
        )
        table = document.add_table(rows=1, cols=len(desc_stats.columns) + 1)
        table.style = "Table Grid"
        hdr_cells = table.rows[0].cells
        hdr_cells[0].text = "group_id"
        for i, col_name in enumerate(desc_stats.columns):
            hdr_cells[i + 1].text = col_name
        for index, row in desc_stats.iterrows():
            row_cells = table.add_row().cells
            row_cells[0].text = str(index)
            for i, value in enumerate(row):
                row_cells[i + 1].text = f"{value:.2f}"

        document.add_page_break()
        document.add_heading("Gráficos Comparativos", level=2)
        boxplot_fig = Reporter._generate_comparative_boxplot(
            aggregated_df,
            "distancia_total_cm",
            "Comparação da Distância Total Percorrida por Grupo",
        )
        with io.BytesIO() as memfile:
            boxplot_fig.savefig(memfile, format="png", dpi=300)
            memfile.seek(0)
            document.add_picture(memfile, width=Inches(6.0))
        plt.close(boxplot_fig)

        file_path = f"{output_path}.docx"
        document.save(file_path)
        print(f"Relatório de projeto salvo em: {file_path}")
