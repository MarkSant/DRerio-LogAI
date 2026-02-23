"""Interactive HTML report generation with Plotly.

Creates a standalone HTML file with interactive, zoomable plots that can
be shared via email or web hosting.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd
import structlog

if TYPE_CHECKING:
    from zebtrack.analysis.reporters.reporter_context import ReporterContext

log = structlog.get_logger(__name__)


class HtmlReporter:
    """Generate an interactive HTML report using Plotly.

    Example:
        >>> ctx = ReporterContext.from_analysis(analysis_result)
        >>> HtmlReporter(ctx).export_interactive_html_report("report.html")
    """

    def __init__(self, ctx: ReporterContext) -> None:
        self._ctx = ctx

    def export_interactive_html_report(self, output_path: Path | str) -> None:
        """Generate interactive HTML report with Plotly visualisations.

        Features:
            - Interactive trajectory plot with velocity colourmap
            - Velocity over time with freezing episodes highlighted
            - ROI occupancy bar chart
            - Hoverable tooltips with detailed information

        Args:
            output_path: Output file path for the HTML report.

        Raises:
            ImportError: If ``plotly`` is not installed.
            ValueError: If ``BehaviorAnalyzer`` is not available.
        """
        try:
            import plotly.graph_objects as go
            from plotly.subplots import make_subplots
        except ImportError:
            log.error(
                "reporter.plotly_not_installed",
                message="Plotly is required for interactive HTML reports. "
                "Install with: pip install plotly",
            )
            raise ImportError("Plotly is not installed. Run: pip install plotly") from None

        output_path = Path(output_path) if isinstance(output_path, str) else output_path

        if self._ctx.b_analyzer is None:
            raise ValueError("BehaviorAnalyzer not available. Cannot generate HTML report.")

        trajectory_df = self._ctx.b_analyzer.trajectory_data

        fig = make_subplots(
            rows=2,
            cols=2,
            subplot_titles=(
                "Trajectory (Color = Velocity)",
                "Velocity Over Time",
                "ROI Time Spent",
                "Freezing Episodes",
            ),
            specs=[
                [{"type": "scatter"}, {"type": "scatter"}],
                [{"type": "bar"}, {"type": "scatter"}],
            ],
            vertical_spacing=0.12,
            horizontal_spacing=0.1,
        )

        # 1. Trajectory plot (top-left)
        if "x_cm" in trajectory_df.columns and "y_cm" in trajectory_df.columns:
            velocity = self._ctx.b_analyzer.calculate_velocity_timeseries()["v_mag"]
            fig.add_trace(
                go.Scatter(
                    x=trajectory_df["x_cm"],
                    y=trajectory_df["y_cm"],
                    mode="lines+markers",
                    name="Trajectory",
                    marker=dict(
                        size=4,
                        color=velocity,
                        colorscale="Viridis",
                        colorbar=dict(title="Velocity (cm/s)", x=0.46),
                        showscale=True,
                    ),
                    line=dict(width=1),
                    hovertemplate=(
                        "<b>Position</b><br>X: %{x:.2f} cm<br>Y: %{y:.2f} cm<br>"
                        "Velocity: %{marker.color:.2f} cm/s<extra></extra>"
                    ),
                ),
                row=1,
                col=1,
            )
            fig.update_xaxis(title_text="X Position (cm)", row=1, col=1)
            fig.update_yaxis(title_text="Y Position (cm)", row=1, col=1)

        # 2. Velocity over time (top-right)
        velocity_ts = self._ctx.b_analyzer.calculate_velocity_timeseries()["v_mag"]
        fps = float((self._ctx.metadata or {}).get("fps", 30.0) or 30.0)
        time_seconds = trajectory_df.index.to_numpy() / fps
        fig.add_trace(
            go.Scatter(
                x=time_seconds,
                y=velocity_ts,
                mode="lines",
                name="Velocity",
                line=dict(color="blue", width=1.5),
                hovertemplate=(
                    "<b>Velocity</b><br>Time: %{x:.2f} s<br>Speed: %{y:.2f} cm/s<extra></extra>"
                ),
            ),
            row=1,
            col=2,
        )

        freezing_threshold = self._ctx.freezing_threshold or 1.5
        fig.add_hline(
            y=freezing_threshold,
            line_dash="dash",
            line_color="red",
            annotation_text=f"Freezing Threshold ({freezing_threshold} cm/s)",
            row=1,
            col=2,
        )
        fig.update_xaxis(title_text="Time (seconds)", row=1, col=2)
        fig.update_yaxis(title_text="Velocity (cm/s)", row=1, col=2)

        # 3. ROI time spent (bottom-left)
        if self._ctx.r_analyzer is not None:
            roi_time = self._ctx.r_analyzer.get_time_spent_in_rois()
            if roi_time:
                roi_names = list(roi_time.keys())
                roi_values = [roi_time[name] for name in roi_names]

                fig.add_trace(
                    go.Bar(
                        x=roi_names,
                        y=roi_values,
                        name="ROI Time",
                        marker=dict(color="lightblue"),
                        hovertemplate="<b>%{x}</b><br>Time: %{y:.2f} s<extra></extra>",
                    ),
                    row=2,
                    col=1,
                )
                fig.update_xaxis(title_text="ROI Name", row=2, col=1)
                fig.update_yaxis(title_text="Time Spent (seconds)", row=2, col=1)

        # 4. Freezing episodes (bottom-right)
        freezing_list = self._ctx.b_analyzer.detect_freezing_episodes(
            min_duration=self._ctx.freezing_duration or 1.0,
            vel_threshold=freezing_threshold,
        )
        freezing_episodes = pd.DataFrame(freezing_list)

        if not freezing_episodes.empty:
            fps = float((self._ctx.metadata or {}).get("fps", 30.0) or 30.0)
            freeze_times = freezing_episodes["start_frame"].to_numpy() / fps
            freeze_durations = freezing_episodes["duration_s"].to_numpy()

            fig.add_trace(
                go.Scatter(
                    x=freeze_times,
                    y=freeze_durations,
                    mode="markers",
                    name="Freezing Episodes",
                    marker=dict(size=10, color="red", symbol="circle"),
                    hovertemplate=(
                        "<b>Freezing Episode</b><br>Start: %{x:.2f} s<br>"
                        "Duration: %{y:.2f} s<extra></extra>"
                    ),
                ),
                row=2,
                col=2,
            )
            fig.update_xaxis(title_text="Time (seconds)", row=2, col=2)
            fig.update_yaxis(title_text="Duration (seconds)", row=2, col=2)

        # Layout
        metadata = self._ctx.metadata or {}
        experiment_id = metadata.get("experiment_id", "Unknown")
        subject_id = metadata.get("subject_id", "Unknown")

        fig.update_layout(
            title_text=(f"Interactive Analysis Report - {experiment_id} (Subject: {subject_id})"),
            title_font_size=20,
            showlegend=False,
            height=900,
            width=1400,
            hovermode="closest",
        )

        html_path = str(output_path).replace(".html", "") + ".html"
        fig.write_html(
            html_path,
            config={
                "displayModeBar": True,
                "toImageButtonOptions": {
                    "format": "png",
                    "filename": f"report_{experiment_id}",
                    "height": 900,
                    "width": 1400,
                    "scale": 2,
                },
                "modeBarButtonsToAdd": ["hoverclosest", "hovercompare"],
            },
            include_plotlyjs="cdn",
        )

        log.info(
            "reporter.interactive_html_exported",
            path=html_path,
            experiment_id=experiment_id,
        )
