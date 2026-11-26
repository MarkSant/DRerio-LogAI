"""Barnes-maze aggregates for the partial, batch and unified reports (#633).

Learning curves (group x day), search-strategy distribution (group x day) and the probe
comparison (group), computed from the ``barnes_*`` tidy columns every Barnes summary
carries. Nothing here recomputes a metric: a row is one trial that ``AnalysisService``
already measured.

Censoring (``docs/reference/metrics.md`` 7.3). A censored latency is the trial ceiling,
a lower bound and not a measurement. Every latency aggregate therefore carries three
things next to its mean: ``n``, ``n_censored`` and ``mean_observed`` (the mean of the
uncensored trials only). The plotted mean counts a censored trial at the ceiling, the
usual convention for a Barnes learning curve, and the figures and tables say how many
trials that concerns; a missing latency (``None``: probe trial, no entry rule) is never
a zero and never counts as a trial. An empty cell stays empty (``NaN``), never ``0``.

Two frames feed this module: the unified report reads the parquet summaries
(``barnes_*`` internal names, ``group_id`` / ``day``) and the partial report reads the
individual ``.xlsx`` (display names, ``grupo`` / ``dia``); :func:`to_internal_columns`
maps the second onto the first.
"""

from __future__ import annotations

import io
import math
import re
from collections.abc import Callable
from typing import Any, Final

import numpy as np
import pandas as pd
import structlog
from docx.document import Document as DocxDocument
from docx.shared import Inches
from matplotlib.figure import Figure

from zebtrack.analysis.data_transformer import (
    BARNES_COLUMN_PREFIX,
    DISPLAY_COLUMN_MAPPING,
)
from zebtrack.analysis.reporters.reporter_context import _

log = structlog.get_logger(__name__)

__all__ = [
    "LEARNING_METRICS",
    "PROBE_METRICS",
    "STRATEGIES",
    "barnes_sheets",
    "is_barnes_frame",
    "learning_curves",
    "probe_comparison",
    "render_barnes_aggregates",
    "render_barnes_per_animal",
    "strategy_distribution",
    "to_internal_columns",
]

#: Search strategies in display order (persistence tokens, never translated as stored).
STRATEGIES: Final[tuple[str, ...]] = ("direct", "serial", "random")

#: Learning-curve metrics: (key, value column, censored column or None, is a latency).
LEARNING_METRICS: Final[tuple[tuple[str, str, str | None], ...]] = (
    ("encounter_latency_s", "barnes_encounter_latency_s", "barnes_encounter_censored"),
    ("entry_latency_s", "barnes_entry_latency_s", "barnes_entry_censored"),
    ("primary_errors", "barnes_primary_errors", None),
    ("total_errors", "barnes_total_errors", None),
)

#: Probe metrics: (key, source column). ``first_hole_distance`` is derived (|offset|).
PROBE_METRICS: Final[tuple[tuple[str, str], ...]] = (
    ("first_hole_score", "barnes_probe_first_hole_score"),
    ("first_hole_distance", "barnes_probe_first_hole_offset"),
    ("first_error_latency_s", "barnes_probe_first_error_latency_s"),
    ("attempts_to_target", "barnes_probe_attempts_to_target"),
    ("target_quadrant_pct", "barnes_target_quadrant_pct"),
)

_VISITS_DISPLAY_RE = re.compile(r"^Barnes Visits at Distance (\d+)$")


# ---------------------------------------------------------------------------
# Frame helpers
# ---------------------------------------------------------------------------


def to_internal_columns(df: pd.DataFrame) -> pd.DataFrame:
    """``df`` with the Barnes DISPLAY column names mapped back to the internal ones.

    The individual ``.xlsx`` (what the partial report reads) carries display names
    (``Barnes Primary Errors``); the parquet summary (what the unified report reads)
    carries the internal ones (``barnes_primary_errors``). A frame already in internal
    names comes back unchanged.
    """
    inverse = {
        display: internal
        for internal, display in DISPLAY_COLUMN_MAPPING.items()
        if internal.startswith(BARNES_COLUMN_PREFIX)
    }
    rename: dict[str, str] = {}
    for column in df.columns:
        if column in inverse:
            rename[column] = inverse[column]
            continue
        match = _VISITS_DISPLAY_RE.match(str(column))
        if match is not None:
            rename[column] = f"barnes_visits_d{int(match.group(1)):02d}"
    return df.rename(columns=rename) if rename else df


def is_barnes_frame(df: pd.DataFrame) -> bool:
    """Whether the frame belongs to a Barnes project (has the ``barnes_status`` column).

    A Barnes project's summaries ALWAYS have the ``barnes_*`` columns (CONTRACTS
    section 8) and a generic project's never do, so the column is the discriminator
    for readers that only have the aggregated frame.
    """
    return "barnes_status" in to_internal_columns(df).columns


def _bool_series(series: pd.Series) -> pd.Series:
    """A True/False series where anything else (NaN, None, strings) is False."""
    return series.map(lambda v: v is True or v == 1 or str(v).lower() == "true").astype(bool)


def _numeric(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series(np.nan, index=df.index, dtype=float)
    return pd.to_numeric(df[column], errors="coerce")


def _day_key(value: Any) -> tuple[float, str]:
    """Natural sort key of a day label: ``Dia_2`` before ``Dia_10``."""
    text = str(value)
    match = re.search(r"\d+", text)
    return (float(match.group()) if match else math.inf, text)


def _sem(values: pd.Series) -> float:
    """Standard error of the mean; ``NaN`` with fewer than two values (never 0)."""
    values = values.dropna()
    if len(values) < 2:
        return float("nan")
    return float(values.std(ddof=1) / math.sqrt(len(values)))


def _mean(values: pd.Series) -> float:
    values = values.dropna()
    return float(values.mean()) if len(values) else float("nan")


def _ok_trials(df: pd.DataFrame, trial_type: str | None) -> pd.DataFrame:
    """The trials of ``trial_type`` whose Barnes metrics were computed."""
    internal = to_internal_columns(df)
    if "barnes_status" not in internal.columns:
        return internal.iloc[0:0]
    mask = internal["barnes_status"].astype("string") == "ok"
    if trial_type is not None and "barnes_trial_type" in internal.columns:
        mask &= internal["barnes_trial_type"].astype("string") == trial_type
    return internal.loc[mask.fillna(False)]


def _groups(
    df: pd.DataFrame, group_col: str, day_col: str | None
) -> list[tuple[Any, Any, pd.DataFrame]]:
    """``(group, day, rows)`` per block, groups in first-seen order, days naturally sorted."""
    if day_col is None or day_col not in df.columns:
        return [(g, None, rows) for g, rows in df.groupby(group_col, sort=False, dropna=False)]
    blocks = [
        (g, d, rows) for (g, d), rows in df.groupby([group_col, day_col], sort=False, dropna=False)
    ]
    order = {g: i for i, g in enumerate(dict.fromkeys(df[group_col]))}
    return sorted(blocks, key=lambda b: (order[b[0]], _day_key(b[1])))


# ---------------------------------------------------------------------------
# Aggregates
# ---------------------------------------------------------------------------

_CURVE_COLUMNS = (
    "group",
    "day",
    "metric",
    "n",
    "n_censored",
    "mean",
    "sem",
    "mean_observed",
)


def learning_curves(
    df: pd.DataFrame, *, group_col: str = "group_id", day_col: str | None = "day"
) -> pd.DataFrame:
    """Training-trial learning curves: one row per (group, day, metric).

    ``n`` counts the trials that have a value (a missing latency is not a trial),
    ``n_censored`` those whose latency is the trial ceiling, ``mean`` / ``sem`` use the
    values as stored (a censored latency counts at the ceiling) and ``mean_observed``
    uses the uncensored trials only. An error count has ``n_censored == 0``.
    """
    training = _ok_trials(df, "training")
    rows: list[dict[str, Any]] = []
    if group_col in training.columns:
        for group, day, block in _groups(training, group_col, day_col):
            for key, column, censored_column in LEARNING_METRICS:
                values = _numeric(block, column)
                censored = (
                    _bool_series(block[censored_column])
                    if censored_column is not None and censored_column in block.columns
                    else pd.Series(False, index=block.index)
                )
                present = values.notna()
                rows.append(
                    {
                        "group": group,
                        "day": day,
                        "metric": key,
                        "n": int(present.sum()),
                        "n_censored": int((censored & present).sum()),
                        "mean": _mean(values),
                        "sem": _sem(values),
                        "mean_observed": _mean(values.where(~censored)),
                    }
                )
    return pd.DataFrame(rows, columns=list(_CURVE_COLUMNS))


def strategy_distribution(
    df: pd.DataFrame, *, group_col: str = "group_id", day_col: str | None = "day"
) -> pd.DataFrame:
    """Search strategy per (group, day) over training trials that have one.

    Columns ``group, day, strategy, n, n_trials, fraction``: ``n_trials`` is the number
    of trials with a strategy in the block (a trial with no hole visited has none and
    is not in the denominator), ``fraction`` is ``n / n_trials``.
    """
    training = _ok_trials(df, "training")
    rows: list[dict[str, Any]] = []
    if group_col in training.columns and "barnes_strategy" in training.columns:
        for group, day, block in _groups(training, group_col, day_col):
            strategies = block["barnes_strategy"].astype("string").dropna()
            total = len(strategies)
            if not total:
                continue
            for strategy in STRATEGIES:
                n = int((strategies == strategy).sum())
                rows.append(
                    {
                        "group": group,
                        "day": day,
                        "strategy": strategy,
                        "n": n,
                        "n_trials": total,
                        "fraction": n / total,
                    }
                )
    return pd.DataFrame(rows, columns=["group", "day", "strategy", "n", "n_trials", "fraction"])


def probe_comparison(df: pd.DataFrame, *, group_col: str = "group_id") -> pd.DataFrame:
    """Probe-trial metrics per group: ``group, metric, n, mean, sem``.

    ``first_hole_distance`` is ``|offset|`` of the first hole visited. A metric that
    is ``None`` for a trial (no error before the target, target never reached) is not
    counted for that trial, so ``n`` can be smaller than the number of probes.
    """
    probes = _ok_trials(df, "probe")
    rows: list[dict[str, Any]] = []
    if group_col in probes.columns:
        for group, block in probes.groupby(group_col, sort=False, dropna=False):
            for key, column in PROBE_METRICS:
                values = _numeric(block, column)
                if key == "first_hole_distance":
                    values = values.abs()
                rows.append(
                    {
                        "group": group,
                        "metric": key,
                        "n": int(values.notna().sum()),
                        "mean": _mean(values),
                        "sem": _sem(values),
                    }
                )
    return pd.DataFrame(rows, columns=["group", "metric", "n", "mean", "sem"])


def barnes_sheets(
    df: pd.DataFrame, *, group_col: str = "group_id", day_col: str | None = "day"
) -> dict[str, pd.DataFrame]:
    """The aggregate tables as workbook sheets (empty ones are left out).

    Sheet names are English persistence tokens: third-party scripts open the workbook
    by name, so they never change with the interface language.
    """
    tables = {
        "barnes_learning_curves": learning_curves(df, group_col=group_col, day_col=day_col),
        "barnes_strategy": strategy_distribution(df, group_col=group_col, day_col=day_col),
        "barnes_probe": probe_comparison(df, group_col=group_col),
    }
    return {name: table for name, table in tables.items() if not table.empty}


# ---------------------------------------------------------------------------
# Figures (object-oriented matplotlib: no pyplot state, safe in any thread)
# ---------------------------------------------------------------------------


def _metric_title(key: str) -> str:
    titles: dict[str, Callable[[], str]] = {
        "encounter_latency_s": lambda: _("Encounter latency (s)"),
        "entry_latency_s": lambda: _("Entry latency (s)"),
        "primary_errors": lambda: _("Primary errors"),
        "total_errors": lambda: _("Total errors"),
        "first_hole_score": lambda: _("First hole score"),
        "first_hole_distance": lambda: _("First hole distance"),
        "first_error_latency_s": lambda: _("First error latency (s)"),
        "attempts_to_target": lambda: _("Attempts to target"),
        "target_quadrant_pct": lambda: _("Target quadrant time (%)"),
    }
    return titles[key]() if key in titles else key


def learning_curve_figure(curves: pd.DataFrame) -> Figure | None:
    """Mean +/- SEM per day, one line per group, one panel per metric.

    A point with censored trials is drawn hollow and labelled ``k/n`` (censored of
    trials): its mean counts those trials at the ceiling and is a lower bound.
    ``None`` when there is nothing to draw.
    """
    if curves.empty:
        return None
    figure = Figure(figsize=(9.0, 6.5), layout="constrained")
    axes = figure.subplots(2, 2).ravel()
    groups = list(dict.fromkeys(curves["group"]))
    days = sorted({d for d in curves["day"] if d is not None}, key=_day_key)
    for ax, (key, _column, _censored) in zip(axes, LEARNING_METRICS, strict=True):
        ax.set_title(_metric_title(key), fontsize=10)
        for index, group in enumerate(groups):
            rows = curves[(curves["metric"] == key) & (curves["group"] == group)]
            rows = rows.sort_values("day", key=lambda s: s.map(_day_key))
            x = [days.index(d) if d in days else 0 for d in rows["day"]]
            colour = f"C{index % 10}"
            ax.errorbar(
                x,
                rows["mean"],
                yerr=rows["sem"].fillna(0.0),
                color=colour,
                marker="o",
                capsize=3,
                label=str(group),
            )
            for xi, (_idx, row) in zip(x, rows.iterrows(), strict=True):
                if row["n_censored"] > 0 and not math.isnan(row["mean"]):
                    ax.plot(xi, row["mean"], "o", mfc="white", mec=colour, ms=9, zorder=3)
                    ax.annotate(
                        f"{int(row['n_censored'])}/{int(row['n'])}",
                        (xi, row["mean"]),
                        textcoords="offset points",
                        xytext=(0, 8),
                        ha="center",
                        fontsize=7,
                    )
        if days:
            ax.set_xticks(range(len(days)), [str(d) for d in days], fontsize=8)
        ax.set_ylim(bottom=0)
        ax.grid(alpha=0.3)
    axes[0].legend(fontsize=8, title=_("Group"), title_fontsize=8)
    figure.suptitle(_("Learning curves (mean ± SEM; hollow = censored trials, k/n)"), fontsize=11)
    return figure


def strategy_figure(distribution: pd.DataFrame) -> Figure | None:
    """Stacked bars of the strategy fractions, one bar per (group, day)."""
    if distribution.empty:
        return None
    labels: list[str] = []
    blocks: list[pd.DataFrame] = []
    for (group, day), block in distribution.groupby(["group", "day"], sort=False, dropna=False):
        labels.append(f"{group}\n{day}" if day is not None and not pd.isna(day) else str(group))
        blocks.append(block)
    figure = Figure(figsize=(max(5.5, 0.9 * len(labels) + 2.5), 4.5), layout="constrained")
    ax = figure.subplots()
    colours = {"direct": "#2e7d32", "serial": "#f9a825", "random": "#c62828"}
    bottoms = np.zeros(len(blocks))
    for strategy in STRATEGIES:
        heights = np.array(
            [float(b.loc[b["strategy"] == strategy, "fraction"].sum()) for b in blocks]
        )
        ax.bar(
            range(len(blocks)),
            heights,
            bottom=bottoms,
            color=colours[strategy],
            label=_strategy_title(strategy),
        )
        bottoms += heights
    for index, block in enumerate(blocks):
        ax.annotate(
            f"n={int(block['n_trials'].iloc[0])}",
            (index, 1.0),
            textcoords="offset points",
            xytext=(0, 3),
            ha="center",
            fontsize=8,
        )
    ax.set_xticks(range(len(labels)), labels, fontsize=8)
    ax.set_ylim(0, 1.12)
    ax.set_ylabel(_("Fraction of trials"))
    ax.set_title(_("Search strategy by group and day"), fontsize=11)
    ax.legend(fontsize=8, loc="upper left", bbox_to_anchor=(1.01, 1.0))
    return figure


def _strategy_title(strategy: str) -> str:
    titles: dict[str, Callable[[], str]] = {
        "direct": lambda: _("Direct"),
        "serial": lambda: _("Serial"),
        "random": lambda: _("Random"),
    }
    return titles[strategy]()


def probe_figure(probe: pd.DataFrame) -> Figure | None:
    """Mean +/- SEM per group for the first-hole score and the target-quadrant time."""
    if probe.empty:
        return None
    figure = Figure(figsize=(8.0, 3.8), layout="constrained")
    axes = figure.subplots(1, 2)
    groups = list(dict.fromkeys(probe["group"]))
    for ax, key in zip(axes, ("first_hole_score", "target_quadrant_pct"), strict=True):
        rows = probe[probe["metric"] == key].set_index("group").reindex(groups)
        ax.bar(
            range(len(groups)),
            rows["mean"].fillna(0.0),
            yerr=rows["sem"].fillna(0.0),
            capsize=4,
            color=[f"C{i % 10}" for i in range(len(groups))],
        )
        for index, group in enumerate(groups):
            n = rows.loc[group, "n"]
            ax.annotate(
                f"n={0 if pd.isna(n) else int(n)}",
                (index, 0),
                textcoords="offset points",
                xytext=(0, 3),
                ha="center",
                fontsize=8,
            )
        ax.set_xticks(range(len(groups)), [str(g) for g in groups], fontsize=8)
        ax.set_title(_metric_title(key), fontsize=10)
        ax.grid(axis="y", alpha=0.3)
    figure.suptitle(_("Probe trial by group (mean ± SEM)"), fontsize=11)
    return figure


# ---------------------------------------------------------------------------
# Word rendering (shared by the unified and the partial report)
# ---------------------------------------------------------------------------


def _mean_sem(mean: Any, sem: Any, *, digits: int = 2) -> str:
    """``mean ± sem``; an empty mean is N/A and an undefined SEM is left out."""
    if mean is None or pd.isna(mean):
        return _("N/A")
    text = f"{float(mean):.{digits}f}"
    if sem is None or pd.isna(sem):
        return text
    return f"{text} ± {float(sem):.{digits}f}"


def _curve_cell(row: pd.Series, *, latency: bool) -> str:
    text = _mean_sem(row["mean"], row["sem"])
    if latency and row["n_censored"] > 0:
        text += " " + _("[{censored}/{n} censored]").format(
            censored=int(row["n_censored"]), n=int(row["n"])
        )
    return text


def _add_figure(document: DocxDocument, figure: Figure | None, width: float = 6.0) -> None:
    if figure is None:
        return
    buffer = io.BytesIO()
    figure.savefig(buffer, format="png", dpi=200)
    buffer.seek(0)
    document.add_picture(buffer, width=Inches(width))


def _day_text(day: Any) -> str:
    return "" if day is None or pd.isna(day) else str(day)


def _render_curve_table(document: DocxDocument, curves: pd.DataFrame) -> None:
    blocks = curves[["group", "day"]].drop_duplicates()
    headers = [_("Group"), _("Day")] + [
        _metric_title(key) for key, _column, _censored in LEARNING_METRICS
    ]
    table = document.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    for cell, title in zip(table.rows[0].cells, headers, strict=True):
        cell.text = title
    for _index, block in blocks.iterrows():
        cells = table.add_row().cells
        cells[0].text = str(block["group"])
        cells[1].text = _day_text(block["day"])
        for position, (key, _column, censored_column) in enumerate(LEARNING_METRICS, start=2):
            match = curves[
                (curves["group"] == block["group"])
                & (curves["metric"] == key)
                & ((curves["day"] == block["day"]) | (curves["day"].isna() & pd.isna(block["day"])))
            ]
            cells[position].text = (
                _curve_cell(match.iloc[0], latency=censored_column is not None)
                if len(match)
                else _("N/A")
            )


def _render_strategy_table(document: DocxDocument, distribution: pd.DataFrame) -> None:
    headers = [_("Group"), _("Day"), _("Trials")] + [_strategy_title(s) for s in STRATEGIES]
    table = document.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    for cell, title in zip(table.rows[0].cells, headers, strict=True):
        cell.text = title
    for (group, day), block in distribution.groupby(["group", "day"], sort=False, dropna=False):
        cells = table.add_row().cells
        cells[0].text = str(group)
        cells[1].text = _day_text(day)
        cells[2].text = str(int(block["n_trials"].iloc[0]))
        for position, strategy in enumerate(STRATEGIES, start=3):
            row = block[block["strategy"] == strategy].iloc[0]
            cells[position].text = f"{int(row['n'])} ({100.0 * float(row['fraction']):.0f}%)"


def _render_probe_table(document: DocxDocument, probe: pd.DataFrame) -> None:
    keys = [key for key, _column in PROBE_METRICS]
    headers = [_("Group")] + [_metric_title(key) for key in keys]
    table = document.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    for cell, title in zip(table.rows[0].cells, headers, strict=True):
        cell.text = title
    for group in dict.fromkeys(probe["group"]):
        cells = table.add_row().cells
        cells[0].text = str(group)
        for position, key in enumerate(keys, start=1):
            rows = probe[(probe["group"] == group) & (probe["metric"] == key)]
            if rows.empty:
                cells[position].text = _("N/A")
                continue
            row = rows.iloc[0]
            cells[position].text = (
                f"{_mean_sem(row['mean'], row['sem'])} (n={int(row['n'])})"
                if row["n"]
                else _("N/A")
            )


def render_barnes_aggregates(
    document: DocxDocument,
    df: pd.DataFrame,
    *,
    group_col: str = "group_id",
    day_col: str | None = "day",
    with_figures: bool = True,
) -> bool:
    """Append the Barnes aggregates to ``document``; ``False`` when ``df`` is not Barnes.

    Nothing is written for a generic frame. For a Barnes frame the section is always
    written (a Barnes project with no computed trial says so), so a reader never has to
    guess whether the aggregates were skipped.
    """
    if not is_barnes_frame(df):
        return False
    frame = to_internal_columns(df)
    document.add_heading(_("Barnes Maze Results"), level=2)
    curves = learning_curves(frame, group_col=group_col, day_col=day_col)
    strategies = strategy_distribution(frame, group_col=group_col, day_col=day_col)
    probes = probe_comparison(frame, group_col=group_col)
    if curves.empty and strategies.empty and probes.empty:
        document.add_paragraph(_("No Barnes trial with computed metrics is in this report."))
        return True

    if not curves.empty:
        document.add_heading(_("Learning curves"), level=3)
        document.add_paragraph(
            _(
                "Training trials, mean ± SEM per group and day. A censored latency "
                "(the event did not happen before the end of the trial) is counted at "
                "the trial ceiling: it is a lower bound, not a measurement. The number "
                "of censored trials is shown next to each latency."
            )
        )
        _render_curve_table(document, curves)
        if with_figures and curves["day"].nunique(dropna=True) > 1:
            _add_figure(document, learning_curve_figure(curves))
    if not strategies.empty:
        document.add_heading(_("Search strategy"), level=3)
        _render_strategy_table(document, strategies)
        if with_figures:
            _add_figure(document, strategy_figure(strategies), width=5.5)
    if not probes.empty:
        document.add_heading(_("Probe trial"), level=3)
        _render_probe_table(document, probes)
        if with_figures:
            _add_figure(document, probe_figure(probes), width=5.5)
    return True


def render_barnes_per_animal(
    document: DocxDocument, df: pd.DataFrame, *, animal_col: str = "animal"
) -> bool:
    """One row per animal with its headline Barnes metrics (the partial report).

    ``False`` for a generic frame (nothing written). A censored latency is written as
    ``>= value`` and a missing one as N/A: neither is ever shown as ``0``. The strategy
    says whether a researcher corrected it.
    """
    if not is_barnes_frame(df):
        return False
    frame = to_internal_columns(df)
    document.add_heading(_("Barnes Maze Results per Animal"), level=2)
    if animal_col not in frame.columns or frame.empty:
        document.add_paragraph(_("No Barnes trial with computed metrics is in this report."))
        return True

    headers = [
        _("Animal"),
        _("Trial"),
        _("Encounter latency (s)"),
        _("Entry latency (s)"),
        _("Primary errors"),
        _("Total errors"),
        _("Search strategy"),
    ]
    table = document.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    for cell, title in zip(table.rows[0].cells, headers, strict=True):
        cell.text = title
    for _index, row in frame.iterrows():
        cells = table.add_row().cells
        cells[0].text = str(row[animal_col])
        if str(row.get("barnes_status")) != "ok":
            cells[1].text = _("Status: {status}").format(status=row.get("barnes_status"))
            for cell in cells[2:]:
                cell.text = _("N/A")
            continue
        cells[1].text = _trial_text(row.get("barnes_trial_type"))
        cells[2].text = _latency_cell(
            row.get("barnes_encounter_latency_s"), row.get("barnes_encounter_censored")
        )
        cells[3].text = _latency_cell(
            row.get("barnes_entry_latency_s"), row.get("barnes_entry_censored")
        )
        cells[4].text = _count_cell(row.get("barnes_primary_errors"))
        cells[5].text = _count_cell(row.get("barnes_total_errors"))
        cells[6].text = _strategy_cell(
            row.get("barnes_strategy"), row.get("barnes_strategy_source")
        )
    return True


def _trial_text(trial_type: Any) -> str:
    if trial_type == "probe":
        return _("Probe")
    if trial_type == "training":
        return _("Training")
    return _("N/A")


def _latency_cell(value: Any, censored: Any) -> str:
    if value is None or pd.isna(value):
        return _("N/A")
    if censored is True or str(censored).lower() == "true":
        return _("≥ {value:.2f} s (censored)").format(value=float(value))
    return f"{float(value):.2f}"


def _count_cell(value: Any) -> str:
    return _("N/A") if value is None or pd.isna(value) else str(int(value))


def _strategy_cell(strategy: Any, source: Any) -> str:
    if strategy is None or pd.isna(strategy):
        return _("N/A")
    label = _strategy_title(str(strategy)) if str(strategy) in STRATEGIES else str(strategy)
    return _("{strategy} (corrected)").format(strategy=label) if source == "manual" else label
