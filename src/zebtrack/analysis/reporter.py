import io
from datetime import datetime
from pathlib import Path
import cv2

import matplotlib.patches as patches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

# Assume these are in the same directory for standalone testing
from docx import Document
from docx.shared import Inches
from scipy.ndimage import gaussian_filter

from zebtrack.analysis.behavior import ConcreteBehavioralAnalyzer
from zebtrack.analysis.roi import ROIAnalyzer


class Reporter:
    def __init__(
        self,
        b_analyzer: ConcreteBehavioralAnalyzer,
        r_analyzer: ROIAnalyzer,
        metadata: dict,
        roi_colors: dict | None = None,
        video_path: str | None = None,
        sharp_turn_threshold: float = 90.0,
        freezing_threshold: float = 2.0,
        freezing_duration: float = 1.0,
    ):
        self.b_analyzer = b_analyzer
        self.r_analyzer = r_analyzer
        self.metadata = metadata
        self.roi_colors = roi_colors if roi_colors else {}
        self.video_path = video_path
        self.sharp_turn_threshold = sharp_turn_threshold
        self.freezing_threshold = freezing_threshold
        self.freezing_duration = freezing_duration
        self.tidy_data = self._create_tidy_dataframe()

    def _create_tidy_dataframe(self) -> pd.DataFrame:
        # Start with metadata
        combined_data = {**self.metadata}

        # --- General Behavioral Metrics ---
        combined_data["total_distance_cm"] = self.b_analyzer.calculate_total_distance()
        velocity_stats = self.b_analyzer.get_velocity_stats()
        combined_data["mean_velocity_cm_s"] = velocity_stats.get("mean")
        combined_data["median_velocity_cm_s"] = velocity_stats.get("median")
        combined_data["std_dev_velocity_cm_s"] = velocity_stats.get("std_dev")
        sharp_turn_results = self.b_analyzer.calculate_sharp_turns(
            self.sharp_turn_threshold
        )
        combined_data["sharp_turns_count"] = sharp_turn_results.get("sharp_turns_count")
        combined_data["sharp_turns_per_minute"] = sharp_turn_results.get(
            "sharp_turns_per_minute"
        )

        # --- ROI-Specific Metrics ---
        time_spent = self.r_analyzer.get_time_spent_in_rois()
        entry_counts = self.r_analyzer.get_entry_counts()
        exit_counts = self.r_analyzer.get_exit_counts()
        latencies = self.r_analyzer.get_latency_to_first_entry()
        distances = self.r_analyzer.get_distance_in_rois()
        velocities = self.r_analyzer.get_velocity_stats_in_rois()
        freezing = self.r_analyzer.get_freezing_in_rois(
            self.freezing_threshold, self.freezing_duration
        )

        total_roi_entries = 0
        for roi_name in self.r_analyzer._rois:
            # Time spent
            combined_data[f"time_in_{roi_name}_s"] = time_spent.get(roi_name, {}).get(
                "seconds"
            )
            combined_data[
                f"time_in_{roi_name}_percent"
            ] = time_spent.get(roi_name, {}).get("percentage")
            # Entry and Exit counts
            entries = entry_counts.get(roi_name, 0)
            combined_data[f"entries_in_{roi_name}"] = entries
            total_roi_entries += entries
            combined_data[f"exits_from_{roi_name}"] = exit_counts.get(roi_name, 0)
            # Latency
            combined_data[f"latency_to_{roi_name}_s"] = latencies.get(roi_name)
            # Intra-ROI Distance
            combined_data[f"distance_in_{roi_name}_cm"] = distances.get(roi_name)
            # Intra-ROI Velocity
            roi_vel = velocities.get(roi_name)
            if roi_vel:
                combined_data[f"mean_velocity_in_{roi_name}_cm_s"] = roi_vel.get("mean")
            # Intra-ROI Freezing
            roi_freeze = freezing.get(roi_name)
            if roi_freeze:
                combined_data[f"freezing_episodes_in_{roi_name}"] = roi_freeze.get(
                    "count"
                )
                combined_data[
                    f"total_freezing_duration_in_{roi_name}_s"
                ] = roi_freeze.get("total_duration")
            # ROI Color
            if roi_name in self.roi_colors:
                combined_data[f"cor_roi_{roi_name}"] = str(self.roi_colors[roi_name])

        combined_data["total_roi_entries"] = total_roi_entries
        combined_data["date_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return pd.DataFrame([combined_data])

    def export_summary_data(self, output_path: str, format: str = "excel"):
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if format == "excel":
            self.tidy_data.to_excel(output_path, index=False, engine="openpyxl")
        elif format == "csv":
            self.tidy_data.to_csv(output_path, index=False)
        elif format == "parquet":
            self.tidy_data.to_parquet(output_path, index=False)
        else:
            raise ValueError(f"Unsupported file format: {format}")

    def generate_trajectory_plot(
        self, ax: plt.Axes = None, video_path: str | None = None
    ) -> plt.Figure:
        fig = ax.get_figure() if ax else plt.figure(figsize=(6, 6))
        ax = ax or fig.add_subplot(111)
        ax.clear()

        traj_data = self.b_analyzer._trajectory_data
        x = traj_data["x_cm_smoothed"]
        y = traj_data["y_cm_smoothed"]
        arena_poly_cm = self.b_analyzer._arena_polygon_cm
        min_x, min_y, max_x, max_y = arena_poly_cm.bounds

        if video_path and Path(video_path).exists():
            cap = cv2.VideoCapture(video_path)
            ret, frame = cap.read()
            cap.release()
            if ret:
                ax.imshow(
                    cv2.cvtColor(frame, cv2.COLOR_BGR2RGB),
                    extent=(min_x, max_x, min_y, max_y),
                    aspect='auto'
                )

        ax.set_facecolor("lightgray")
        ax.add_patch(
            patches.Polygon(
                arena_poly_cm.exterior.coords, fill=False, edgecolor="black", lw=2
            )
        )
        from matplotlib.collections import LineCollection
        points = np.array([x, y]).T.reshape(-1, 1, 2)
        segments = np.concatenate([points[:-1], points[1:]], axis=1)
        lc = LineCollection(segments, cmap="viridis", norm=plt.Normalize(0, len(x)))
        lc.set_array(np.arange(len(x)))
        ax.add_collection(lc)
        ax.set_title(f"Trajectory - {self.metadata.get('experiment_id', 'N/A')}")
        ax.set_xlim(min_x - 1, max_x + 1)
        ax.set_ylim(min_y - 1, max_y + 1)
        ax.set_aspect("equal", adjustable="box")
        return fig

    def generate_heatmap(self, ax: plt.Axes = None) -> plt.Figure:
        fig = ax.get_figure() if ax else plt.figure(figsize=(6, 6))
        ax = ax or fig.add_subplot(111)
        ax.clear()

        traj_data = self.b_analyzer._trajectory_data
        x = traj_data["x_cm_smoothed"]
        y = traj_data["y_cm_smoothed"]
        arena_poly_cm = self.b_analyzer._arena_polygon_cm
        min_x, min_y, max_x, max_y = arena_poly_cm.bounds

        heatmap, xedges, yedges = np.histogram2d(
            x, y, bins=50, range=[[min_x, max_x], [min_y, max_y]]
        )
        heatmap = gaussian_filter(heatmap.T, sigma=2)
        im = ax.imshow(
            heatmap,
            cmap="hot",
            origin="lower",
            extent=[xedges[0], xedges[-1], yedges[0], yedges[-1]],
        )
        ax.set_title(f"Heatmap - {self.metadata.get('experiment_id', 'N/A')}")
        ax.set_xlim(min_x -1, max_x + 1)
        ax.set_ylim(min_y-1, max_y+1)
        ax.set_aspect("equal", adjustable="box")
        if not any(isinstance(artist, plt.colorbar.Colorbar) for artist in fig.artists):
            fig.colorbar(im, ax=ax)
        return fig

    def generate_roi_reference_plot(self, ax: plt.Axes = None) -> plt.Figure:
        fig = ax.get_figure() if ax else plt.figure(figsize=(6, 6))
        ax = ax or fig.add_subplot(111)
        ax.clear()

        arena_poly_cm = self.b_analyzer._arena_polygon_cm
        min_x, min_y, max_x, max_y = arena_poly_cm.bounds

        ax.set_facecolor("lightgray")
        ax.add_patch(
            patches.Polygon(
                arena_poly_cm.exterior.coords, fill=False, edgecolor="black", lw=2
            )
        )

        for i, (roi_name, roi) in enumerate(self.r_analyzer._rois.items()):
            roi_color = self.roi_colors.get(roi_name, 'blue')
            ax.add_patch(
                patches.Polygon(
                    roi.geometry.exterior.coords, fill=True, color=roi_color, alpha=0.4
                )
            )
            centroid = roi.geometry.centroid
            ax.text(centroid.x, centroid.y, str(i + 1),
                    color='white', ha='center', va='center',
                    fontweight='bold', fontsize=12,
                    bbox=dict(facecolor=roi_color, alpha=0.7, boxstyle='circle,pad=0.2', ec='none'))

        ax.set_title(f"ROI Reference Map - {self.metadata.get('experiment_id', 'N/A')}")
        ax.set_xlim(min_x - 1, max_x + 1)
        ax.set_ylim(min_y - 1, max_y + 1)
        ax.set_aspect("equal", adjustable="box")
        return fig

    def generate_angular_velocity_plot(self, ax: plt.Axes = None) -> plt.Figure:
        fig = ax.get_figure() if ax else plt.figure(figsize=(12, 6))
        ax = ax or fig.add_subplot(111)
        ax.clear()

        angular_velocity = self.b_analyzer.get_angular_velocity()
        if angular_velocity.empty or angular_velocity.isna().all():
            ax.text(0.5, 0.5, "Not enough data for angular velocity.", ha='center', va='center')
            ax.set_title("Angular Velocity")
            return fig

        sharp_turn_results = self.b_analyzer.calculate_sharp_turns(self.sharp_turn_threshold)
        sharp_turn_times = sharp_turn_results["sharp_turns_timestamps"]

        time_seconds = (angular_velocity.index - angular_velocity.index[0]).total_seconds()

        ax.plot(time_seconds, angular_velocity, label="Angular Velocity")

        if not sharp_turn_times.empty:
            sharp_turn_values = angular_velocity.loc[sharp_turn_times]
            sharp_turn_time_seconds = (sharp_turn_times - angular_velocity.index[0]).total_seconds()
            ax.plot(sharp_turn_time_seconds, sharp_turn_values, 'ro', markersize=5, label="Sharp Turns")

        ax.set_title(f"Angular Velocity - {self.metadata.get('experiment_id', 'N/A')}")
        ax.set_xlabel("Time (s)")
        ax.set_ylabel("Angular Velocity (deg/s)")
        ax.legend()
        ax.grid(True)
        return fig

    def generate_position_vs_time_plot(self, ax: plt.Axes = None) -> plt.Figure:
        fig = ax.get_figure() if ax else plt.figure(figsize=(12, 6))
        ax = ax or fig.add_subplot(111)
        ax.clear()

        traj_data = self.b_analyzer._trajectory_data
        if traj_data.empty:
            ax.text(0.5, 0.5, "No trajectory data.", ha='center', va='center')
            ax.set_title("Position vs. Time")
            return fig

        time_seconds = (traj_data.index - traj_data.index[0]).total_seconds()

        ax.plot(time_seconds, traj_data["x_cm_smoothed"], label="X coordinate (cm)")
        ax.plot(time_seconds, traj_data["y_cm_smoothed"], label="Y coordinate (cm)")

        ax.set_title(f"Position vs. Time - {self.metadata.get('experiment_id', 'N/A')}")
        ax.set_xlabel("Time (s)")
        ax.set_ylabel("Position (cm)")
        ax.legend()
        ax.grid(True)
        return fig

    def generate_cumulative_distance_plot(self, ax: plt.Axes = None) -> plt.Figure:
        fig = ax.get_figure() if ax else plt.figure(figsize=(12, 6))
        ax = ax or fig.add_subplot(111)
        ax.clear()

        traj_data = self.b_analyzer._trajectory_data
        if len(traj_data) < 2:
            ax.text(0.5, 0.5, "Not enough data for distance calculation.", ha='center', va='center')
            ax.set_title("Cumulative Distance")
            return fig

        distances = np.sqrt(
            traj_data["x_cm_smoothed"].diff() ** 2 + traj_data["y_cm_smoothed"].diff() ** 2
        )
        cumulative_distance = distances.cumsum().fillna(0)
        time_seconds = (traj_data.index - traj_data.index[0]).total_seconds()

        ax.plot(time_seconds, cumulative_distance)
        ax.set_title(f"Cumulative Distance vs. Time - {self.metadata.get('experiment_id', 'N/A')}")
        ax.set_xlabel("Time (s)")
        ax.set_ylabel("Cumulative Distance (cm)")
        ax.grid(True)
        return fig

    def export_individual_report(self, output_path: str):
        document = Document()
        document.add_heading(
            f"Analysis Report - {self.metadata.get('experiment_id', 'N/A')}", level=1
        )
        document.add_heading("Experiment Metadata", level=2)
        for key, value in self.metadata.items():
            document.add_paragraph(f"{key.replace('_', ' ').title()}: {value}")
        document.add_heading("Metrics Summary Table", level=2)
        df = self.tidy_data.drop(
            columns=[k for k in self.metadata.keys() if k in self.tidy_data.columns]
        )
        table = document.add_table(rows=1, cols=len(df.columns))
        table.style = 'Table Grid'
        for i, column_name in enumerate(df.columns):
            table.cell(0, i).text = column_name
        for _, row in df.iterrows():
            cells = table.add_row().cells
            for i, value in enumerate(row):
                cells[i].text = (
                    f"{value:.2f}" if isinstance(value, (int, float)) else str(value)
                )
        document.add_page_break()

        # Add ROI Reference Map first
        document.add_heading("ROI Reference Map", level=2)
        fig = self.generate_roi_reference_plot()
        memfile = io.BytesIO()
        fig.savefig(memfile, format='png', dpi=300, bbox_inches='tight')
        plt.close(fig)
        memfile.seek(0)
        document.add_picture(memfile, width=Inches(5.0))

        document.add_heading("Visualizations", level=2)
        plot_configs = [
            (lambda ax: self.generate_trajectory_plot(ax, self.video_path), "Trajectory"),
            (self.generate_heatmap, "Heatmap"),
            (self.generate_position_vs_time_plot, "Position vs. Time"),
            (self.generate_cumulative_distance_plot, "Cumulative Distance"),
            (self.generate_angular_velocity_plot, "Angular Velocity"),
        ]
        for plot_func, name in plot_configs:
            fig, ax = plt.subplots(figsize=(10, 6))
            plot_func(ax)
            memfile = io.BytesIO()
            fig.savefig(memfile, format='png', dpi=300, bbox_inches='tight')
            plt.close(fig)
            memfile.seek(0)
            document.add_paragraph(f"Chart: {name}:")
            document.add_picture(memfile, width=Inches(6.0))

        document.add_page_break()
        document.add_heading("Appendix: ROI Event Log", level=2)
        event_log_df = self.r_analyzer.get_event_log()

        if not event_log_df.empty:
            document.add_paragraph(
                "Chronological log of all entries and exits from defined ROIs."
            )
            table = document.add_table(rows=1, cols=len(event_log_df.columns))
            table.style = "Table Grid"
            for i, col_name in enumerate(event_log_df.columns):
                table.cell(0, i).text = str(col_name)
            for _, row in event_log_df.iterrows():
                cells = table.add_row().cells
                for i, value in enumerate(row):
                    if isinstance(value, pd.Timestamp):
                        cells[i].text = value.strftime("%H:%M:%S.%f")[:-3]
                    else:
                        cells[i].text = str(value)
        else:
            document.add_paragraph("No ROI entry or exit events were recorded.")

        file_path = f"{output_path}"
        document.save(file_path)
        print(f"Individual report saved to: {file_path}")

    @staticmethod
    def _generate_comparative_boxplot(
        df: pd.DataFrame, metric: str, title: str
    ) -> plt.Figure:
        fig, ax = plt.subplots(figsize=(8, 6))
        sns.boxplot(x="group_id", y=metric, data=df, ax=ax)
        sns.stripplot(x='group_id', y=metric, data=df, ax=ax, color=".25", size=6)
        ax.set_title(title, fontsize=16)
        ax.set_xlabel("Experimental Group", fontsize=12)
        ax.set_ylabel(metric.replace('_', ' ').title(), fontsize=12)
        plt.tight_layout()
        return fig

    @staticmethod
    def export_project_report(aggregated_df: pd.DataFrame, output_path: str):
        document = Document()
        document.add_heading("Aggregated Project Report", level=1)
        document.add_heading("Descriptive Statistics by Group", level=2)
        desc_stats = aggregated_df.groupby("group_id")["distancia_total_cm"].agg(
            ["mean", "std", "count"]
        )
        document.add_paragraph("Statistics for Total Distance Traveled (cm):")
        table = document.add_table(rows=1, cols=len(desc_stats.columns) + 1)
        table.style = 'Table Grid'
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
        document.add_heading("Comparative Plots", level=2)

        metrics_for_boxplot = [
            "total_distance_cm",
            "mean_velocity_cm_s",
            "sharp_turns_count",
            "sharp_turns_per_minute",
            "total_roi_entries"
        ]

        for metric in metrics_for_boxplot:
            if metric in aggregated_df.columns:
                title = f"Comparison of {metric.replace('_', ' ').title()}"
                boxplot_fig = Reporter._generate_comparative_boxplot(
                    aggregated_df,
                    metric,
                    title,
                )
                memfile = io.BytesIO()
                boxplot_fig.savefig(memfile, format='png', dpi=300, bbox_inches='tight')
                plt.close(boxplot_fig)
                memfile.seek(0)
                document.add_paragraph(title, style='Heading 3')
                document.add_picture(memfile, width=Inches(6.0))

        file_path = f"{output_path}.docx"
        document.save(file_path)
        print(f"Project report saved to: {file_path}")
