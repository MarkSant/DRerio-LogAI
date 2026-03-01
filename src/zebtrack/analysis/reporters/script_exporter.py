"""R / Python / Feather export utilities.

Provides methods to export the tidy analysis DataFrame in formats
suitable for R (Feather, CSV, ``.R`` script template) and Python
(Parquet, Feather, ``.py`` notebook template).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from zebtrack.analysis.reporters.reporter_context import ReporterContext

log = structlog.get_logger(__name__)


class ScriptExporter:
    """Export data and analysis script templates for R and Python.

    Example:
        >>> ctx = ReporterContext.from_analysis(analysis_result)
        >>> ScriptExporter(ctx).export_for_r("output/r_data")
        >>> ScriptExporter(ctx).export_for_python("output/py_data")
    """

    def __init__(self, ctx: ReporterContext) -> None:
        self._ctx = ctx

    # ------------------------------------------------------------------
    # Public API — R
    # ------------------------------------------------------------------
    def export_for_r(
        self,
        output_path: Path | str,
        include_script: bool = True,
    ) -> dict[str, Path]:
        """Export data in R-friendly formats (Feather + CSV + script).

        Args:
            output_path: Directory to export files to.
            include_script: If ``True``, includes a template R script.

        Returns:
            Dictionary with paths to created files.
        """
        import pyarrow.feather as feather

        output_dir = Path(output_path) if isinstance(output_path, str) else output_path
        output_dir.mkdir(parents=True, exist_ok=True)

        created_files: dict[str, Path] = {}

        feather_path = output_dir / "data.feather"
        feather.write_feather(self._ctx.tidy_data, feather_path, compression="zstd")
        created_files["feather"] = feather_path
        log.info("reporter.export_r.feather_saved", path=str(feather_path))

        csv_path = output_dir / "data.csv"
        self._ctx.tidy_data.to_csv(csv_path, index=False)
        created_files["csv"] = csv_path

        if include_script:
            script_path = output_dir / "analysis_script.R"
            r_script = self._generate_r_script_template()
            script_path.write_text(r_script, encoding="utf-8")
            created_files["script"] = script_path
            log.info("reporter.export_r.script_saved", path=str(script_path))

        log.info(
            "reporter.export_r.complete",
            output_dir=str(output_dir),
            files=list(created_files.keys()),
        )
        return created_files

    # ------------------------------------------------------------------
    # Public API — Python
    # ------------------------------------------------------------------
    def export_for_python(
        self,
        output_path: Path | str,
        include_script: bool = True,
    ) -> dict[str, Path]:
        """Export data in Python-friendly formats (Parquet + Feather + script).

        Args:
            output_path: Directory to export files to.
            include_script: If ``True``, includes a template Python script.

        Returns:
            Dictionary with paths to created files.
        """
        import pyarrow.feather as feather

        output_dir = Path(output_path) if isinstance(output_path, str) else output_path
        output_dir.mkdir(parents=True, exist_ok=True)

        created_files: dict[str, Path] = {}

        parquet_path = output_dir / "data.parquet"
        self._ctx.tidy_data.to_parquet(parquet_path, index=False)
        created_files["parquet"] = parquet_path
        log.info("reporter.export_python.parquet_saved", path=str(parquet_path))

        feather_path = output_dir / "data.feather"
        feather.write_feather(self._ctx.tidy_data, feather_path, compression="zstd")
        created_files["feather"] = feather_path

        if include_script:
            script_path = output_dir / "analysis_notebook.py"
            py_script = self._generate_python_script_template()
            script_path.write_text(py_script, encoding="utf-8")
            created_files["script"] = script_path
            log.info("reporter.export_python.script_saved", path=str(script_path))

        log.info(
            "reporter.export_python.complete",
            output_dir=str(output_dir),
            files=list(created_files.keys()),
        )
        return created_files

    # ------------------------------------------------------------------
    # Convenience aliases
    # ------------------------------------------------------------------
    def export_feather(self, output_path: Path | str) -> Path:
        """Export data as Feather format for fast R/Python loading.

        Args:
            output_path: Path to the output ``.feather`` file.

        Returns:
            Path to the created Feather file.
        """
        import pyarrow.feather as feather

        output_file = Path(output_path) if isinstance(output_path, str) else output_path
        output_file.parent.mkdir(parents=True, exist_ok=True)

        feather.write_feather(self._ctx.tidy_data, output_file, compression="zstd")
        log.info("reporter.export_feather.saved", path=str(output_file))
        return output_file

    def export_r_script(self, output_path: Path | str) -> Path:
        """Export template R script for statistical analysis.

        Args:
            output_path: Path to the output ``.R`` file.

        Returns:
            Path to the created R script file.
        """
        output_file = Path(output_path) if isinstance(output_path, str) else output_path
        output_file.parent.mkdir(parents=True, exist_ok=True)

        r_script = self._generate_r_script_template()
        output_file.write_text(r_script, encoding="utf-8")
        log.info("reporter.export_r_script.saved", path=str(output_file))
        return output_file

    def export_python_script(self, output_path: Path | str) -> Path:
        """Export template Python script for Jupyter/VS Code analysis.

        Args:
            output_path: Path to the output ``.py`` file.

        Returns:
            Path to the created Python script file.
        """
        output_file = Path(output_path) if isinstance(output_path, str) else output_path
        output_file.parent.mkdir(parents=True, exist_ok=True)

        py_script = self._generate_python_script_template()
        output_file.write_text(py_script, encoding="utf-8")
        log.info("reporter.export_python_script.saved", path=str(output_file))
        return output_file

    # ------------------------------------------------------------------
    # Template generators (private)
    # ------------------------------------------------------------------
    def _generate_r_script_template(self) -> str:
        """Generate template R script for data analysis."""
        return """# ZebTrack-AI Analysis Script for R
# Generated automatically - customize as needed

# Required packages
if (!require("arrow")) install.packages("arrow")
if (!require("ggplot2")) install.packages("ggplot2")
if (!require("dplyr")) install.packages("dplyr")

library(arrow)
library(ggplot2)
library(dplyr)

# Load data (Feather is fastest, CSV is universal fallback)
data <- arrow::read_feather("data.feather")
# Alternative: data <- read.csv("data.csv")

# Preview data structure
str(data)
summary(data)

# ============================================================
# Basic Movement Analysis
# ============================================================

# Calculate total distance per subject
distance_summary <- data %>%
  group_by(subject_id) %>%
  summarise(
    total_distance_cm = sum(velocity_cm_s * (1/30), na.rm = TRUE),  # 30 fps
    mean_velocity = mean(velocity_cm_s, na.rm = TRUE),
    max_velocity = max(velocity_cm_s, na.rm = TRUE),
    time_in_center_pct = mean(in_center_roi, na.rm = TRUE) * 100
  )

print(distance_summary)

# ============================================================
# Trajectory Plot
# ============================================================

ggplot(data, aes(x = x_cm, y = y_cm, color = as.factor(subject_id))) +
  geom_path(alpha = 0.5) +
  labs(
    title = "Zebrafish Trajectories",
    x = "X Position (cm)",
    y = "Y Position (cm)",
    color = "Subject"
  ) +
  theme_minimal()

# ============================================================
# Velocity Over Time
# ============================================================

ggplot(data, aes(x = timestamp, y = velocity_cm_s)) +
  geom_line(alpha = 0.5) +
  geom_smooth(method = "loess", se = TRUE) +
  labs(
    title = "Velocity Over Time",
    x = "Time (seconds)",
    y = "Velocity (cm/s)"
  ) +
  theme_minimal()

# ============================================================
# Statistical Tests (Example)
# ============================================================

# If you have experimental groups, add group column and run tests
# Example:
# t.test(velocity_cm_s ~ group, data = data)
# wilcox.test(velocity_cm_s ~ group, data = data)
"""

    def _generate_python_script_template(self) -> str:
        """Generate template Python script for data analysis."""
        return """# %% [markdown]
# # ZebTrack-AI Analysis Notebook
# Generated automatically - customize as needed

# %% [markdown]
# ## Load Data

# %%
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

# Load data (Parquet is fastest)
df = pd.read_parquet("data.parquet")
# Alternative: df = pd.read_feather("data.feather")

# Preview data
print(f"Shape: {df.shape}")
print(f"Columns: {list(df.columns)}")
df.head()

# %%
df.describe()

# %% [markdown]
# ## Basic Movement Analysis

# %%
# Calculate summary statistics per subject
summary = df.groupby("subject_id").agg({
    "velocity_cm_s": ["mean", "max", "std"],
    "x_cm": ["min", "max"],
    "y_cm": ["min", "max"],
}).round(2)

summary.columns = ["_".join(col) for col in summary.columns]
print(summary)

# %% [markdown]
# ## Trajectory Visualization

# %%
fig, ax = plt.subplots(figsize=(10, 8))

for subject_id in df["subject_id"].unique():
    subject_data = df[df["subject_id"] == subject_id]
    ax.plot(
        subject_data["x_cm"],
        subject_data["y_cm"],
        alpha=0.6,
        label=f"Subject {subject_id}"
    )

ax.set_xlabel("X Position (cm)")
ax.set_ylabel("Y Position (cm)")
ax.set_title("Zebrafish Trajectories")
ax.legend()
ax.set_aspect("equal")
plt.tight_layout()
plt.show()

# %% [markdown]
# ## Velocity Analysis

# %%
fig, axes = plt.subplots(1, 2, figsize=(14, 5))

# Velocity over time
ax1 = axes[0]
ax1.plot(df["timestamp"], df["velocity_cm_s"], alpha=0.3, linewidth=0.5)
# Rolling average
rolling = df["velocity_cm_s"].rolling(window=30, min_periods=1).mean()
ax1.plot(df["timestamp"], rolling, color="red", linewidth=2, label="30-frame avg")
ax1.set_xlabel("Time (s)")
ax1.set_ylabel("Velocity (cm/s)")
ax1.set_title("Velocity Over Time")
ax1.legend()

# Velocity distribution
ax2 = axes[1]
ax2.hist(df["velocity_cm_s"].dropna(), bins=50, edgecolor="black", alpha=0.7)
ax2.axvline(df["velocity_cm_s"].mean(), color="red", linestyle="--", label="Mean")
ax2.set_xlabel("Velocity (cm/s)")
ax2.set_ylabel("Frequency")
ax2.set_title("Velocity Distribution")
ax2.legend()

plt.tight_layout()
plt.show()

# %% [markdown]
# ## Export Results

# %%
# Save summary to CSV for further analysis
summary.to_csv("analysis_summary.csv")
print("Summary saved to analysis_summary.csv")

# %% [markdown]
# ## Statistical Tests (Add Your Groups)

# %%
# If you have experimental groups, uncomment and modify:
# from scipy import stats
#
# group_a = df[df["group"] == "control"]["velocity_cm_s"]
# group_b = df[df["group"] == "treatment"]["velocity_cm_s"]
#
# t_stat, p_value = stats.ttest_ind(group_a, group_b)
# print(f"T-test: t={t_stat:.3f}, p={p_value:.4f}")
"""
