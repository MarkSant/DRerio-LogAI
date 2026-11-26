"""Validate and calibrate the Barnes-maze metrics against the lab's manual scoring (#633).

The lab scores each trial by hand and keeps the numbers in spreadsheets (latencies of
encounter and entry, search strategy, probe). This tool puts the app's numbers next to
them and says how well they agree, so the provisional ``BarnesParams`` thresholds can be
calibrated on evidence instead of guessed. Full guide: ``docs/tasks/v8.1/barnes/VALIDATION.md``.

Modes (``python scripts/barnes_validation.py <mode> --help``)::

    init-mapping  Write a documented example mapping file (the layout of the lab's sheets).
    validate      Compare the lab sheets with the app's unified report (``--unified``).
    recompute     Re-run ONLY the analysis on existing results (``--results-root``), with
                  optional BarnesParams overrides (``--set key=value``); with a mapping,
                  validate the result. Never runs detection and never writes into the
                  results: the analysis runs on private copies of the trajectories.
    calibrate     Grid-search the thresholds on a calibration subset, report the agreement
                  on a held-out subset, and print a suggested ``protocol_params.barnes``
                  block. Never overwrites the project's settings.

Conventions that hold in every report:

* **App minus lab**: every difference is ``app - lab``.
* **Censored values are not observations.** A latency of 240 s means "did not happen within
  the ceiling" (the lab's rule for rats that do not enter or are placed by hand; the app's
  ``*_censored`` flag). Agreement statistics are computed on pairs where BOTH sides observed
  the event; the censoring agreement is reported on its own, and a second, clearly labelled
  "ceiling-imputed" view keeps the censored pairs at the ceiling so the effect is visible.
* **Strategy is compared with the app's automatic result** (``barnes_strategy_auto``), never
  with the manually corrected one: a correction made by looking at the lab's answer would
  leak it into the comparison.
* Rows are matched by group/day/subject (or by a video path of two or more components),
  never by an ambiguous basename; rows with no counterpart are listed on both sides.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import sys
import tempfile
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from datetime import time as dt_time
from itertools import product
from pathlib import Path
from typing import Any, Final, Protocol

import numpy as np
import pandas as pd
import structlog
import yaml
from scipy import stats as sp_stats

logger = structlog.get_logger()

# =============================================================================
# Constants
# =============================================================================

#: Protocol ceiling (s): the lab scores "did not enter / placed by hand" as this.
DEFAULT_CENSOR_AT_S: Final = 240.0
_CENSOR_TOLERANCE_S: Final = 1e-6

SHEET_NAMES: Final = ("latencies", "strategy", "probe")

#: Canonical columns a lab sheet may map, per sheet. ``video``/``group``/``day``/``subject``
#: identify the row; ``start_time_s`` is the manual START.
SHEET_FIELDS: Final[dict[str, tuple[str, ...]]] = {
    "latencies": (
        "video",
        "group",
        "day",
        "subject",
        "start_time_s",
        "encounter_latency_s",
        "entry_latency_s",
        "encounter_censored",
        "entry_censored",
        "primary_errors",
        "total_errors",
    ),
    "strategy": ("video", "group", "day", "subject", "start_time_s", "strategy"),
    "probe": (
        "video",
        "group",
        "day",
        "subject",
        "start_time_s",
        "probe_score",
        "first_error_latency_s",
        "attempts",
    ),
}
_IDENTITY_FIELDS: Final = ("video", "group", "day", "subject")
_TIME_FIELDS: Final = (
    "start_time_s",
    "encounter_latency_s",
    "entry_latency_s",
    "first_error_latency_s",
)
_COUNT_FIELDS: Final = ("primary_errors", "total_errors", "probe_score", "attempts")
_FLAG_FIELDS: Final = ("encounter_censored", "entry_censored")

#: Metric fields (not identity) each sheet needs at least one of.
_METRIC_FIELDS: Final[dict[str, tuple[str, ...]]] = {
    name: tuple(f for f in fields if f not in _IDENTITY_FIELDS and f != "start_time_s")
    for name, fields in SHEET_FIELDS.items()
}

STRATEGY_LABELS: Final = ("direct", "serial", "random")
_DEFAULT_STRATEGY_MAP: Final[dict[str, str]] = {
    "direct": "direct",
    "direta": "direct",
    "direto": "direct",
    "serial": "serial",
    "seriada": "serial",
    "serializada": "serial",
    "random": "random",
    "aleatoria": "random",
    "aleatorio": "random",
    "randomica": "random",
    "randomico": "random",
}
_TRUE_TOKENS: Final = frozenset({"1", "true", "sim", "s", "yes", "y", "x", "verdadeiro"})
_FALSE_TOKENS: Final = frozenset({"0", "false", "nao", "n", "no", "falso"})

#: Canonical app columns, in order. ``case`` is the row's identity inside this run.
APP_COLUMNS: Final = (
    "group",
    "day",
    "subject",
    "experiment_id",
    "video_path",
    "status",
    "trial_type",
    "t_start_s",
    "encounter_latency_s",
    "encounter_censored",
    "entry_latency_s",
    "entry_censored",
    "primary_errors",
    "total_errors",
    "strategy_auto",
    "strategy",
    "probe_first_hole_score",
    "probe_first_error_latency_s",
    "probe_attempts_to_target",
)
_APP_NUMERIC: Final = (
    "t_start_s",
    "encounter_latency_s",
    "entry_latency_s",
    "primary_errors",
    "total_errors",
    "probe_first_hole_score",
    "probe_first_error_latency_s",
    "probe_attempts_to_target",
)
_APP_FLAGS: Final = ("encounter_censored", "entry_censored")

#: Where each canonical app column lives in the app's unified summary (``.parquet`` has the
#: raw names; override any of them with ``app.columns`` in the mapping file).
UNIFIED_COLUMNS: Final[dict[str, tuple[str, ...]]] = {
    "group": ("group", "group_id"),
    "day": ("day",),
    "subject": ("subject",),
    "experiment_id": ("experiment_id",),
    "video_path": ("video_path",),
    "status": ("barnes_status",),
    "trial_type": ("barnes_trial_type",),
    "t_start_s": ("window_start_s",),
    "encounter_latency_s": ("barnes_encounter_latency_s",),
    "encounter_censored": ("barnes_encounter_censored",),
    "entry_latency_s": ("barnes_entry_latency_s",),
    "entry_censored": ("barnes_entry_censored",),
    "primary_errors": ("barnes_primary_errors",),
    "total_errors": ("barnes_total_errors",),
    "strategy_auto": ("barnes_strategy_auto",),
    "strategy": ("barnes_strategy",),
    "probe_first_hole_score": ("barnes_probe_first_hole_score",),
    "probe_first_error_latency_s": ("barnes_probe_first_error_latency_s",),
    "probe_attempts_to_target": ("barnes_probe_attempts_to_target",),
}

_ID_PREFIX_RE: Final = re.compile(
    r"^(?:grupo|group|dia|day|sujeito|subject|animal|rato|rat)[\s_\-]*", re.IGNORECASE
)
_FOLDER_RE: Final[dict[str, re.Pattern[str]]] = {
    "group": re.compile(r"^(?:grupo|group)[\s_\-]*(.+)$", re.IGNORECASE),
    "day": re.compile(r"^(?:dia|day)[\s_\-]*(.+)$", re.IGNORECASE),
    "subject": re.compile(r"^(?:sujeito|subject)[\s_\-]*(.+)$", re.IGNORECASE),
}
_TRAJECTORY_PREFIX: Final = "3_CoordMovimento_"
_ARENA_PREFIX: Final = "1_ProcessingArea_"
_ROIS_PREFIX: Final = "2_AreasOfInterest_"

# =============================================================================
# Small utilities
# =============================================================================


class ValidationInputError(ValueError):
    """The mapping file, a sheet or an app file cannot be used (CLI exit code 2)."""


def fold(text: Any) -> str:
    """Lower-case, accent-free, single-spaced form of ``text`` (for tolerant comparisons)."""
    decomposed = unicodedata.normalize("NFKD", str(text))
    plain = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(plain.casefold().split())


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def normalize_token(value: Any) -> str | None:
    """Canonical form of a group/day/subject value so lab and app spellings meet.

    ``"Dia_1"``, ``"dia 1"``, ``1``, ``1.0`` and ``"01"`` all become ``"1"``;
    ``"Grupo_CBD"`` and ``"cbd"`` become ``"cbd"``. ``None`` for blank values.
    """
    if _is_missing(value):
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = fold(value)
    text = _ID_PREFIX_RE.sub("", text).strip(" _-")
    text = re.sub(r"[\s_\-]+", "_", text)
    if not text:
        return None
    if text.isdigit():
        return str(int(text))
    return text


def path_parts(value: Any) -> tuple[str, ...]:
    """Folded components of a path, the last one without its extension.

    Windows and POSIX separators are both honoured, so a path copied from the lab's
    spreadsheet compares equal to the app's.
    """
    if _is_missing(value):
        return ()
    text = str(value).strip().replace("\\", "/")
    parts = [fold(p) for p in text.split("/") if p.strip() and p.strip() != "."]
    if not parts:
        return ()
    last = parts[-1]
    dot = last.rfind(".")
    if dot > 0 and len(last) - dot <= 5:
        parts[-1] = last[:dot]
    return tuple(p for p in parts if not re.fullmatch(r"[a-z]:", p))


def parse_seconds(value: Any) -> float:
    """A time in seconds from a spreadsheet cell; ``nan`` when it is not a time.

    Accepts numbers (seconds), ``"83,5"``, ``"1:23.5"`` / ``"0:01:23"`` (clock form) and
    the time/duration objects Excel cells arrive as. A trailing ``s`` is ignored.
    """
    if _is_missing(value) or isinstance(value, bool):
        return math.nan
    if isinstance(value, int | float | np.integer | np.floating):
        number = float(value)
        return number if math.isfinite(number) else math.nan
    if isinstance(value, timedelta):
        return value.total_seconds()
    if isinstance(value, datetime):
        value = value.time()
    if isinstance(value, dt_time):
        return value.hour * 3600.0 + value.minute * 60.0 + value.second + value.microsecond / 1e6
    text = str(value).strip().lower().rstrip("s").strip().replace(",", ".")
    if not text:
        return math.nan
    try:
        if ":" in text:
            seconds = 0.0
            for chunk in text.split(":"):
                seconds = seconds * 60.0 + float(chunk)
            return seconds
        return float(text)
    except ValueError:
        return math.nan


def parse_flag(value: Any) -> bool | None:
    """``True``/``False`` for a yes/no cell, ``None`` when blank or unrecognised."""
    if _is_missing(value):
        return None
    if isinstance(value, bool | np.bool_):
        return bool(value)
    if isinstance(value, int | float | np.integer | np.floating):
        return bool(value) if value in (0, 1) else None
    token = fold(value)
    if token in _TRUE_TOKENS:
        return True
    if token in _FALSE_TOKENS:
        return False
    return None


def jsonable(value: Any) -> Any:
    """``value`` with numpy/pandas scalars unwrapped and non-finite floats as ``None``."""
    if isinstance(value, Mapping):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [jsonable(v) for v in value]
    if isinstance(value, np.ndarray):
        return [jsonable(v) for v in value.tolist()]
    if isinstance(value, np.bool_ | bool):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, float | np.floating):
        number = float(value)
        return number if math.isfinite(number) else None
    return value


# =============================================================================
# Statistics (pure)
# =============================================================================

_NAN: Final = math.nan

#: Anything numpy can turn into a float vector.
Numbers = Sequence[float] | np.ndarray


@dataclass(frozen=True)
class BlandAltman:
    """Bland-Altman agreement of two measurements of the same quantity.

    Differences are ``app - lab``. ``bias`` is their mean; the 95 % limits of agreement are
    ``bias ± 1.96 · sd_diff`` (Bland & Altman 1986), where ``sd_diff`` is the sample
    standard deviation (ddof = 1). ``bias_ci_*`` is the t-based 95 % interval of the bias.
    """

    n: int
    bias: float
    sd_diff: float
    loa_lower: float
    loa_upper: float
    bias_ci_lower: float
    bias_ci_upper: float
    mean_abs_diff: float


@dataclass(frozen=True)
class IccResult:
    """ICC(2,1): two-way random effects, absolute agreement, single measurement.

    Shrout & Fleiss (1979) case 2 / McGraw & Wong (1996) "A,1", with the two "raters"
    being the lab and the app. With ``n`` pairs and ``k = 2`` raters::

        MSR = between-pairs mean square   MSC = between-raters mean square
        MSE = residual mean square
        ICC(2,1) = (MSR - MSE) / (MSR + (k - 1) MSE + k (MSC - MSE) / n)

    The 95 % interval uses the F approximation of McGraw & Wong. Absolute agreement means a
    constant offset between lab and app LOWERS the ICC (unlike consistency forms).
    """

    n: int
    icc: float
    ci_lower: float
    ci_upper: float


def bland_altman(app: Numbers, lab: Numbers) -> BlandAltman:
    """Bland-Altman statistics of paired ``app`` and ``lab`` values (NaN pairs dropped)."""
    a, b = _paired(app, lab)
    n = len(a)
    if n == 0:
        return BlandAltman(0, _NAN, _NAN, _NAN, _NAN, _NAN, _NAN, _NAN)
    diff = a - b
    bias = float(diff.mean())
    mad = float(np.abs(diff).mean())
    if n < 2:
        return BlandAltman(n, bias, _NAN, _NAN, _NAN, _NAN, _NAN, mad)
    sd = float(diff.std(ddof=1))
    half = float(sp_stats.t.ppf(0.975, n - 1)) * sd / math.sqrt(n)
    return BlandAltman(
        n=n,
        bias=bias,
        sd_diff=sd,
        loa_lower=bias - 1.96 * sd,
        loa_upper=bias + 1.96 * sd,
        bias_ci_lower=bias - half,
        bias_ci_upper=bias + half,
        mean_abs_diff=mad,
    )


def icc_2_1(app: Numbers, lab: Numbers) -> IccResult:
    """ICC(2,1) of paired measurements (see :class:`IccResult`); NaN when undefined."""
    a, b = _paired(app, lab)
    return icc_2_1_matrix(np.column_stack([a, b]) if len(a) else np.empty((0, 2)))


def icc_2_1_matrix(data: np.ndarray) -> IccResult:
    """ICC(2,1) of an ``n x k`` matrix (rows = targets, columns = raters).

    The general form behind :func:`icc_2_1` (k = 2); exposed so the formula can be checked
    against the published Shrout & Fleiss example (k = 4).
    """
    n, k = data.shape
    if n < 3 or k < 2:
        return IccResult(n, _NAN, _NAN, _NAN)
    grand = data.mean()
    ss_rows = k * float(((data.mean(axis=1) - grand) ** 2).sum())
    ss_cols = n * float(((data.mean(axis=0) - grand) ** 2).sum())
    ss_err = float(((data - grand) ** 2).sum()) - ss_rows - ss_cols
    ms_rows = ss_rows / (n - 1)
    ms_cols = ss_cols / (k - 1)
    ms_err = ss_err / ((n - 1) * (k - 1))
    denominator = ms_rows + (k - 1) * ms_err + k * (ms_cols - ms_err) / n
    if denominator <= 0 or not math.isfinite(denominator):
        return IccResult(n, _NAN, _NAN, _NAN)
    icc = (ms_rows - ms_err) / denominator
    if ms_err <= 1e-12:
        return IccResult(n, float(icc), _NAN, _NAN)
    # McGraw & Wong (1996), ICC(A,1): Satterthwaite degrees of freedom, then F limits.
    if icc >= 1.0:
        return IccResult(n, float(icc), _NAN, _NAN)
    a = k * icc / (n * (1.0 - icc))
    b = 1.0 + k * icc * (n - 1) / (n * (1.0 - icc))
    v_den = (a * ms_cols) ** 2 / (k - 1) + (b * ms_err) ** 2 / ((n - 1) * (k - 1))
    if v_den <= 0:
        return IccResult(n, float(icc), _NAN, _NAN)
    v = (a * ms_cols + b * ms_err) ** 2 / v_den
    f_lower_tail = float(sp_stats.f.ppf(0.975, n - 1, v))
    f_upper_tail = float(sp_stats.f.ppf(0.975, v, n - 1))
    pooled = k * ms_cols + (k * n - k - n) * ms_err
    lower = n * (ms_rows - f_lower_tail * ms_err) / (f_lower_tail * pooled + n * ms_rows)
    upper = n * (f_upper_tail * ms_rows - ms_err) / (pooled + n * f_upper_tail * ms_rows)
    return IccResult(n, float(icc), float(lower), float(upper))


def spearman(app: Numbers, lab: Numbers) -> tuple[float, float]:
    """Spearman rank correlation and p-value; ``(nan, nan)`` when undefined (n < 3, constant)."""
    a, b = _paired(app, lab)
    if len(a) < 3 or np.ptp(a) == 0 or np.ptp(b) == 0:
        return _NAN, _NAN
    result = sp_stats.spearmanr(a, b)
    return float(result.statistic), float(result.pvalue)


@dataclass(frozen=True)
class KappaResult:
    """Cohen's kappa of two categorical ratings.

    ``kappa = (p_o - p_e) / (1 - p_e)`` with the observed agreement ``p_o`` and the agreement
    expected from the two raters' marginals ``p_e``. ``ci_*`` use the large-sample standard
    error ``sqrt(p_o (1 - p_o) / (n (1 - p_e)^2))``. ``kappa`` is NaN when ``p_e == 1``
    (both raters used one single label: agreement cannot be told from chance).
    ``matrix[i][j]`` counts rows the LAB called ``labels[i]`` and the APP called ``labels[j]``.
    """

    n: int
    labels: tuple[str, ...]
    matrix: tuple[tuple[int, ...], ...]
    observed_agreement: float
    kappa: float
    ci_lower: float
    ci_upper: float


def cohen_kappa(
    app: Sequence[str], lab: Sequence[str], labels: Sequence[str] = STRATEGY_LABELS
) -> KappaResult:
    """Cohen's kappa and the confusion matrix (rows = lab, columns = app)."""
    names = tuple(labels)
    index = {name: i for i, name in enumerate(names)}
    matrix = np.zeros((len(names), len(names)), dtype=int)
    for app_label, lab_label in zip(app, lab, strict=True):
        if app_label in index and lab_label in index:
            matrix[index[lab_label], index[app_label]] += 1
    n = int(matrix.sum())
    table = tuple(tuple(int(v) for v in row) for row in matrix)
    if n == 0:
        return KappaResult(0, names, table, _NAN, _NAN, _NAN, _NAN)
    observed = float(np.trace(matrix)) / n
    expected = float((matrix.sum(axis=1) * matrix.sum(axis=0)).sum()) / (n * n)
    if math.isclose(expected, 1.0):
        return KappaResult(n, names, table, observed, _NAN, _NAN, _NAN)
    kappa = (observed - expected) / (1.0 - expected)
    se = math.sqrt(max(observed * (1.0 - observed), 0.0) / (n * (1.0 - expected) ** 2))
    return KappaResult(n, names, table, observed, kappa, kappa - 1.96 * se, kappa + 1.96 * se)


def exact_agreement(app: Numbers, lab: Numbers) -> float:
    """Share of pairs whose two values are equal (NaN pairs dropped); NaN with no pair."""
    a, b = _paired(app, lab)
    if len(a) == 0:
        return _NAN
    return float((np.isclose(a, b)).mean())


@dataclass(frozen=True)
class OffsetDistribution:
    """Distribution of ``app START - manual START`` (s); negative = the app starts earlier."""

    n: int
    mean: float
    median: float
    sd: float
    minimum: float
    maximum: float
    p5: float
    p95: float
    within_0_5_s: float
    within_1_s: float
    within_2_s: float


def start_offset_distribution(app_start: Numbers, manual_start: Numbers) -> OffsetDistribution:
    """Distribution of the START offset; the ``within_*`` fields are shares of ``|offset|``."""
    a, b = _paired(app_start, manual_start)
    if len(a) == 0:
        return OffsetDistribution(0, *([_NAN] * 10))
    diff = a - b
    abs_diff = np.abs(diff)
    return OffsetDistribution(
        n=len(diff),
        mean=float(diff.mean()),
        median=float(np.median(diff)),
        sd=float(diff.std(ddof=1)) if len(diff) > 1 else _NAN,
        minimum=float(diff.min()),
        maximum=float(diff.max()),
        p5=float(np.percentile(diff, 5)),
        p95=float(np.percentile(diff, 95)),
        within_0_5_s=float((abs_diff <= 0.5).mean()),
        within_1_s=float((abs_diff <= 1.0).mean()),
        within_2_s=float((abs_diff <= 2.0).mean()),
    )


def _paired(app: Numbers, lab: Numbers) -> tuple[np.ndarray, np.ndarray]:
    a = np.asarray(app, dtype=float)
    b = np.asarray(lab, dtype=float)
    if a.shape != b.shape:
        raise ValueError(f"paired series differ in length: {a.shape} vs {b.shape}")
    keep = np.isfinite(a) & np.isfinite(b)
    return a[keep], b[keep]


# --- comparison blocks (what the reports are built from) ---------------------


def agreement_block(app: Numbers, lab: Numbers) -> dict[str, Any]:
    """Bland-Altman + ICC(2,1) + Spearman of two continuous series, as a plain dict."""
    ba = bland_altman(app, lab)
    icc = icc_2_1(app, lab)
    rho, p_value = spearman(app, lab)
    return {
        "n": ba.n,
        "bland_altman": asdict(ba),
        "icc_2_1": asdict(icc),
        "spearman_rho": rho,
        "spearman_p": p_value,
        "mad": ba.mean_abs_diff,
    }


def count_block(app: Numbers, lab: Numbers) -> dict[str, Any]:
    """Agreement of two integer counts: exact rate, ±1 rate, MAD, bias, Spearman."""
    a, b = _paired(app, lab)
    n = len(a)
    rho, p_value = spearman(a, b)
    return {
        "n": n,
        "exact_agreement": exact_agreement(a, b),
        "within_1": float((np.abs(a - b) <= 1).mean()) if n else _NAN,
        "mad": float(np.abs(a - b).mean()) if n else _NAN,
        "bias": float((a - b).mean()) if n else _NAN,
        "spearman_rho": rho,
        "spearman_p": p_value,
    }


def censoring_block(app_censored: Sequence[bool], lab_censored: Sequence[bool]) -> dict[str, Any]:
    """Agreement of the two censoring flags (``True`` = the event did not happen in time).

    ``lab_only`` counts pairs the lab calls censored and the app observed; ``app_only`` the
    reverse. The kappa is NaN when one side is constant.
    """
    app_flags = ["censored" if c else "observed" for c in app_censored]
    lab_flags = ["censored" if c else "observed" for c in lab_censored]
    kappa = cohen_kappa(app_flags, lab_flags, labels=("observed", "censored"))
    (obs_obs, obs_cen), (cen_obs, cen_cen) = kappa.matrix
    return {
        "n": kappa.n,
        "both_observed": obs_obs,
        "both_censored": cen_cen,
        "lab_only_censored": cen_obs,
        "app_only_censored": obs_cen,
        "agreement": kappa.observed_agreement,
        "kappa": kappa.kappa,
    }


def _as_flags(series: pd.Series) -> np.ndarray:
    """A boolean vector from a True/False/None series (blank counts as ``False``)."""
    return np.array([False if _is_missing(v) else bool(v) for v in series], dtype=bool)


def latency_comparison(
    app: pd.Series,
    app_censored: pd.Series,
    lab: pd.Series,
    lab_censored: pd.Series,
) -> dict[str, Any]:
    """Compare a latency measured by the app with the lab's, censoring handled explicitly.

    Returns ``counts`` (how many pairs and why some are out), ``observed`` (statistics on
    pairs both sides observed — the figure to quote), ``censoring`` (agreement of the two
    flags) and ``ceiling_imputed`` (every pair that has a value, censored ones included at
    the ceiling: NOT observations, shown so the effect of the ceiling can be judged).
    """
    app_values = pd.to_numeric(app, errors="coerce").to_numpy(dtype=float)
    lab_values = pd.to_numeric(lab, errors="coerce").to_numpy(dtype=float)
    app_cens = _as_flags(app_censored)
    lab_cens = _as_flags(lab_censored)
    lab_known = np.isfinite(lab_values) | lab_cens
    app_known = np.isfinite(app_values)
    both = lab_known & app_known
    observed = both & ~app_cens & ~lab_cens & np.isfinite(lab_values)
    counts = {
        "pairs": len(app_values),
        "lab_missing": int((~lab_known).sum()),
        "app_missing": int((lab_known & ~app_known).sum()),
        "compared": int(both.sum()),
        "both_observed": int(observed.sum()),
    }
    return {
        "counts": counts,
        "observed": agreement_block(app_values[observed], lab_values[observed]),
        "censoring": censoring_block(app_cens[both], lab_cens[both]),
        "ceiling_imputed": agreement_block(
            app_values[both], np.where(np.isfinite(lab_values[both]), lab_values[both], np.nan)
        ),
    }


# =============================================================================
# Mapping file and lab sheets
# =============================================================================

EXAMPLE_MAPPING: Final = """\
# Mapping of the lab's exported spreadsheets for scripts/barnes_validation.py.
# Paths are relative to THIS file. Every column value is the header text of the sheet
# (case, accents and surrounding spaces are tolerated). Leave a field out if the lab
# does not record it. Docs: docs/tasks/v8.1/barnes/VALIDATION.md

# How lab rows are matched with the app's results. A row is matched by its video path
# (two or more path components) when the sheet has one, else by the key below. A bare file
# name is NEVER enough on its own (the same name repeats across days) unless you turn
# allow_unique_basename on and the name is unique on both sides.
match:
  keys: [group, day, subject]
  use_video_path: true
  allow_unique_basename: false
  # Optional: lab spelling -> app spelling, per field (after normalisation: "Dia 1" == "1").
  aliases:
    group: {controle: ctrl}

sheets:
  latencies:
    file: latencias.xlsx
    sheet: Plan1            # xlsx only; default: the first sheet
    header_row: 1           # 1-based row with the column titles
    censor_at_s: 240        # a lab latency >= this is "did not happen" (censored)
    columns:
      group: Grupo
      day: Dia
      subject: Animal
      video: Video          # optional: a path with two or more components
      start_time_s: "Inicio (s)"       # the manual START (seconds or m:ss)
      encounter_latency_s: "Latencia encontro (s)"
      entry_latency_s: "Latencia entrada (s)"
      encounter_censored: "Nao encontrou"   # optional yes/no column
      entry_censored: "Nao entrou"          # optional yes/no column
      primary_errors: "Erros primarios"     # optional
      total_errors: "Erros totais"          # optional
  strategy:
    file: estrategia.xlsx
    columns:
      group: Grupo
      day: Dia
      subject: Animal
      strategy: Estrategia
    # lab label -> direct | serial | random (the Portuguese/English defaults are built in)
    label_map:
      direta: direct
      seriada: serial
      aleatoria: random
  probe:
    file: probe.xlsx
    columns:
      group: Grupo
      day: Dia
      subject: Animal
      probe_score: "Score 1o buraco"
      first_error_latency_s: "Latencia 1o erro (s)"
      attempts: "Tentativas"

# Optional: header names of the app's unified summary, only when they differ from the
# parquet's (the .xlsx/.csv exports use display names such as "Experiment ID").
app:
  columns: {}
"""


@dataclass(frozen=True)
class SheetSpec:
    """How to read one lab sheet."""

    name: str
    file: Path
    sheet: str | int | None
    header_row: int
    columns: Mapping[str, str]
    censor_at_s: float
    label_map: Mapping[str, str]
    encoding: str | None = None
    delimiter: str | None = None


@dataclass(frozen=True)
class MatchSpec:
    """How lab rows are matched with the app's rows."""

    keys: tuple[str, ...] = ("group", "day", "subject")
    use_video_path: bool = True
    allow_unique_basename: bool = False
    aliases: Mapping[str, Mapping[str, str]] = field(default_factory=dict)


@dataclass(frozen=True)
class ValidationMapping:
    """The parsed mapping file."""

    sheets: Mapping[str, SheetSpec]
    match: MatchSpec
    app_columns: Mapping[str, str]


def load_mapping(path: str | Path) -> ValidationMapping:
    """Parse and validate a mapping file (YAML or JSON).

    Raises:
        ValidationInputError: unreadable file, unknown sheet/field, or a sheet with no
            identity column / no metric column.
    """
    target = Path(path)
    try:
        text = target.read_text(encoding="utf-8")
        raw = json.loads(text) if target.suffix.lower() == ".json" else yaml.safe_load(text)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        raise ValidationInputError(f"cannot read the mapping file {target}: {exc}") from exc
    if not isinstance(raw, Mapping):
        raise ValidationInputError("the mapping file must be a YAML/JSON object")

    sheets_raw = raw.get("sheets")
    if not isinstance(sheets_raw, Mapping) or not sheets_raw:
        raise ValidationInputError("the mapping needs a non-empty 'sheets' section")
    sheets: dict[str, SheetSpec] = {}
    for name, block in sheets_raw.items():
        if name not in SHEET_NAMES:
            raise ValidationInputError(f"unknown sheet '{name}'; expected one of {SHEET_NAMES}")
        sheets[name] = _parse_sheet(name, block, base=target.parent)

    match_raw = raw.get("match") or {}
    if not isinstance(match_raw, Mapping):
        raise ValidationInputError("'match' must be an object")
    keys = tuple(str(k) for k in match_raw.get("keys", ("group", "day", "subject")))
    bad_keys = [k for k in keys if k not in ("group", "day", "subject")]
    if bad_keys:
        raise ValidationInputError(f"match.keys may only use group/day/subject, got {bad_keys}")
    aliases_raw = match_raw.get("aliases") or {}
    aliases: dict[str, dict[str, str]] = {}
    for field_name, table in aliases_raw.items():
        if field_name not in ("group", "day", "subject") or not isinstance(table, Mapping):
            raise ValidationInputError(f"match.aliases.{field_name} is not a group/day/subject map")
        aliases[field_name] = {
            (normalize_token(k) or ""): (normalize_token(v) or "") for k, v in table.items()
        }
    app_raw = raw.get("app") or {}
    app_columns = {str(k): str(v) for k, v in (app_raw.get("columns") or {}).items()}
    unknown_app = [k for k in app_columns if k not in UNIFIED_COLUMNS]
    if unknown_app:
        raise ValidationInputError(f"app.columns has unknown fields {unknown_app}")
    return ValidationMapping(
        sheets=sheets,
        match=MatchSpec(
            keys=keys,
            use_video_path=bool(match_raw.get("use_video_path", True)),
            allow_unique_basename=bool(match_raw.get("allow_unique_basename", False)),
            aliases=aliases,
        ),
        app_columns=app_columns,
    )


def _parse_sheet(name: str, block: Any, *, base: Path) -> SheetSpec:
    if not isinstance(block, Mapping):
        raise ValidationInputError(f"sheets.{name} must be an object")
    file_value = block.get("file")
    if not file_value:
        raise ValidationInputError(f"sheets.{name}.file is required")
    columns_raw = block.get("columns")
    if not isinstance(columns_raw, Mapping) or not columns_raw:
        raise ValidationInputError(f"sheets.{name}.columns is required")
    allowed = SHEET_FIELDS[name]
    unknown = [k for k in columns_raw if k not in allowed]
    if unknown:
        raise ValidationInputError(
            f"sheets.{name}.columns has unknown fields {unknown}; allowed: {list(allowed)}"
        )
    if not any(f in columns_raw for f in _IDENTITY_FIELDS):
        raise ValidationInputError(
            f"sheets.{name}.columns needs at least one of {list(_IDENTITY_FIELDS)} to identify rows"
        )
    if not any(f in columns_raw for f in _METRIC_FIELDS[name]):
        raise ValidationInputError(
            f"sheets.{name}.columns needs at least one of {list(_METRIC_FIELDS[name])}"
        )
    label_map = dict(_DEFAULT_STRATEGY_MAP)
    for lab_label, canonical in (block.get("label_map") or {}).items():
        if canonical not in STRATEGY_LABELS:
            raise ValidationInputError(
                f"sheets.{name}.label_map maps '{lab_label}' to '{canonical}'; "
                f"use one of {STRATEGY_LABELS}"
            )
        label_map[fold(lab_label)] = str(canonical)
    header_row = int(block.get("header_row", 1))
    if header_row < 1:
        raise ValidationInputError(f"sheets.{name}.header_row is 1-based")
    sheet_value = block.get("sheet")
    return SheetSpec(
        name=name,
        file=(base / str(file_value)).resolve(),
        sheet=sheet_value
        if isinstance(sheet_value, int)
        else (str(sheet_value) if sheet_value else None),
        header_row=header_row,
        columns={str(k): str(v) for k, v in columns_raw.items()},
        censor_at_s=float(block.get("censor_at_s", DEFAULT_CENSOR_AT_S)),
        label_map=label_map,
        encoding=block.get("encoding"),
        delimiter=block.get("delimiter"),
    )


def read_table(
    path: Path,
    *,
    sheet: str | int | None,
    header_row: int,
    encoding: str | None,
    delimiter: str | None,
) -> pd.DataFrame:
    """Read an ``.xlsx``/``.xls``/``.csv``/``.tsv``/``.parquet`` file as text-preserving cells."""
    if not path.is_file():
        raise ValidationInputError(f"file not found: {path}")
    suffix = path.suffix.lower()
    try:
        if suffix in (".xlsx", ".xlsm", ".xls"):
            return pd.read_excel(
                path, sheet_name=sheet if sheet is not None else 0, header=header_row - 1
            )
        if suffix == ".parquet":
            return pd.read_parquet(path)
        if suffix in (".csv", ".tsv", ".txt"):
            return pd.read_csv(
                path,
                sep=delimiter or ("\t" if suffix == ".tsv" else None),
                engine="python",
                encoding=encoding or "utf-8-sig",
                header=header_row - 1,
            )
    except (OSError, ValueError, KeyError) as exc:
        raise ValidationInputError(f"cannot read {path}: {exc}") from exc
    raise ValidationInputError(f"unsupported file type '{suffix}' for {path} (use .xlsx or .csv)")


def _resolve_header(frame: pd.DataFrame, wanted: str, *, where: str) -> str:
    """The real header of ``frame`` that ``wanted`` names (exact, then folded)."""
    headers = [str(c) for c in frame.columns]
    if wanted in headers:
        return wanted
    folded = {fold(h): h for h in headers}
    if fold(wanted) in folded:
        return folded[fold(wanted)]
    raise ValidationInputError(
        f"{where}: column '{wanted}' not found; the sheet has {headers}. "
        "Check the mapping file (and header_row)."
    )


def read_lab_sheet(spec: SheetSpec) -> tuple[pd.DataFrame, list[str]]:
    """Read one lab sheet into canonical columns.

    Returns ``(table, notes)``. The table has ``source_row`` (the sheet's row number, for
    finding the row again), the identity fields, parsed metric fields and, for latencies,
    ``*_censored`` flags (the lab's rule: value >= ``censor_at_s``, or the optional yes/no
    column). ``notes`` lists cells that could not be read (rows kept, value blank).
    """
    frame = read_table(
        spec.file,
        sheet=spec.sheet,
        header_row=spec.header_row,
        encoding=spec.encoding,
        delimiter=spec.delimiter,
    )
    notes: list[str] = []
    out = pd.DataFrame(index=frame.index)
    out["source_row"] = frame.index + spec.header_row + 1
    for canonical, wanted in spec.columns.items():
        header = _resolve_header(frame, wanted, where=f"sheets.{spec.name}")
        column = frame[header]
        if canonical in _TIME_FIELDS:
            parsed = column.map(parse_seconds)
            bad = column.notna() & parsed.isna()
            for row in out.loc[bad, "source_row"]:
                notes.append(f"{spec.name} row {row}: '{wanted}' is not a time; left blank")
            out[canonical] = parsed.astype(float)
        elif canonical in _COUNT_FIELDS:
            out[canonical] = pd.to_numeric(column, errors="coerce").astype(float)
        elif canonical in _FLAG_FIELDS:
            out[canonical] = column.map(parse_flag)
        elif canonical == "strategy":
            out["strategy_raw"] = column
            out["strategy"] = column.map(lambda v: _strategy_label(v, spec.label_map))
            for row, raw, mapped in zip(out["source_row"], column, out["strategy"], strict=True):
                if not _is_missing(raw) and mapped is None:
                    notes.append(f"{spec.name} row {row}: strategy '{raw}' is not in the label map")
        else:
            out[canonical] = column
    for latency, flag in (
        ("encounter_latency_s", "encounter_censored"),
        ("entry_latency_s", "entry_censored"),
    ):
        if latency in out.columns:
            ceiling_hit = out[latency] >= spec.censor_at_s - _CENSOR_TOLERANCE_S
            explicit = out[flag] if flag in out.columns else pd.Series(None, index=out.index)
            out[flag] = [bool(h) or (e is True) for h, e in zip(ceiling_hit, explicit, strict=True)]
    return out, notes


def _strategy_label(value: Any, label_map: Mapping[str, str]) -> str | None:
    if _is_missing(value):
        return None
    return label_map.get(fold(value))


# =============================================================================
# App results
# =============================================================================


def read_unified(
    path: str | Path, overrides: Mapping[str, str] | None = None
) -> tuple[pd.DataFrame, list[str]]:
    """Read the app's unified summary into :data:`APP_COLUMNS`.

    ``path`` is a ``unified*_summary_*.parquet`` (raw column names), or a folder: the newest
    such file below it. A missing column becomes blank and is listed in ``notes`` (for
    example the ``barnes_*`` columns before the reports stage exists in the app version).
    """
    target = Path(path)
    if target.is_dir():
        candidates = sorted(target.rglob("unified*_summary_*.parquet"))
        if not candidates:
            raise ValidationInputError(f"no unified*_summary_*.parquet under {target}")
        target = candidates[-1]
    frame = read_table(target, sheet=None, header_row=1, encoding=None, delimiter=None)
    names = {
        **{k: v for k, v in UNIFIED_COLUMNS.items()},
        **{k: (v,) for k, v in (overrides or {}).items()},
    }
    notes: list[str] = []
    out = pd.DataFrame(index=frame.index)
    for canonical in APP_COLUMNS:
        header = next((h for h in names[canonical] if h in frame.columns), None)
        if header is None:
            if canonical in ("group", "day", "subject", "experiment_id", "video_path"):
                out[canonical] = None
            else:
                out[canonical] = np.nan if canonical in _APP_NUMERIC else None
            notes.append(f"{target.name}: column {names[canonical]} not found ({canonical} blank)")
            continue
        out[canonical] = frame[header]
    return coerce_app_frame(out), notes


def coerce_app_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Types of the canonical app columns: floats for numbers, True/False/None for flags."""
    out = frame.copy()
    for column in _APP_NUMERIC:
        out[column] = pd.to_numeric(out[column], errors="coerce").astype(float)
    for column in _APP_FLAGS:
        out[column] = out[column].map(parse_flag).astype(object)
    for column in ("status", "trial_type", "strategy_auto", "strategy"):
        out[column] = out[column].map(lambda v: None if _is_missing(v) else str(v))
    return out.reset_index(drop=True)


def metrics_row(
    metrics: Mapping[str, Any], *, window_start_s: float | None = None
) -> dict[str, Any]:
    """One canonical app row from a ``report["protocol_metrics"]`` dict.

    A status other than ``ok`` leaves every metric blank (the status is kept, so the report
    can say WHY the app has no value).
    """
    row: dict[str, Any] = {column: None for column in APP_COLUMNS}
    start = math.nan if window_start_s is None else float(window_start_s)
    if metrics.get("status") != "ok":
        row["status"] = f"{metrics.get('status')}:{metrics.get('reason')}"
        for column in _APP_NUMERIC:
            row[column] = math.nan
        row["t_start_s"] = start
        return row
    row.update(
        status="ok",
        trial_type=metrics.get("trial_type"),
        t_start_s=start,
        encounter_latency_s=metrics.get("encounter_latency_s"),
        encounter_censored=metrics.get("encounter_censored"),
        entry_latency_s=metrics.get("entry_latency_s"),
        entry_censored=metrics.get("entry_censored"),
        primary_errors=metrics.get("primary_errors"),
        total_errors=metrics.get("total_errors"),
        strategy_auto=metrics.get("strategy_auto"),
        strategy=metrics.get("strategy"),
        probe_first_hole_score=metrics.get("probe_first_hole_score"),
        probe_first_error_latency_s=metrics.get("probe_first_error_latency_s"),
        probe_attempts_to_target=metrics.get("probe_attempts_to_target"),
    )
    return row


# =============================================================================
# Matching
# =============================================================================


@dataclass
class MatchResult:
    """Outcome of matching one lab sheet with the app rows (indexes are DataFrame labels)."""

    pairs: list[tuple[int, int]] = field(default_factory=list)
    lab_unmatched: list[int] = field(default_factory=list)
    app_unmatched: list[int] = field(default_factory=list)
    ambiguous: list[dict[str, Any]] = field(default_factory=list)
    rules: dict[int, str] = field(default_factory=dict)


def _key_of(
    row: Mapping[str, Any], keys: Sequence[str], aliases: Mapping[str, Mapping[str, str]]
) -> tuple[str, ...] | None:
    values: list[str] = []
    for key in keys:
        token = normalize_token(row.get(key))
        if token is None:
            return None
        values.append(aliases.get(key, {}).get(token, token))
    return tuple(values)


def match_rows(lab: pd.DataFrame, app: pd.DataFrame, spec: MatchSpec) -> MatchResult:
    """Match lab rows with app rows, in this order, first rule with a candidate wins:

    1. **video path** — both sides have a path and the shorter is a suffix of the longer, at
       least two components (so ``Dia_2/CECT_4/CECT_4.mp4`` is not confused with day 1);
    2. **key** — the normalised ``match.keys`` tuple (group/day/subject by default);
    3. **unique basename** — only with ``allow_unique_basename`` and a name that occurs once
       on the lab side and once on the app side.

    A rule with several candidates, or two lab rows claiming one app row, is reported in
    ``ambiguous`` and matched to nothing. Unmatched rows of both sides are listed.
    """
    keys = [k for k in spec.keys if k in lab.columns]
    app_keys = {i: _key_of(app.loc[i], keys, spec.aliases) for i in app.index}
    app_paths = {i: path_parts(app.at[i, "video_path"]) for i in app.index}
    app_stems = {
        i: (path_parts(app.at[i, "video_path"]) or path_parts(app.at[i, "experiment_id"]) or ("",))[
            -1
        ]
        for i in app.index
    }
    lab_stems = {
        i: (path_parts(lab.at[i, "video"]) or ("",))[-1] if "video" in lab.columns else ""
        for i in lab.index
    }
    result = MatchResult()
    claims: dict[int, list[int]] = {}

    for li in lab.index:
        row = lab.loc[li]
        candidates: list[int] = []
        rule = ""
        lab_path = path_parts(row.get("video")) if "video" in lab.columns else ()
        if spec.use_video_path and len(lab_path) >= 2:
            candidates = _closest_paths(lab_path, app_paths)
            rule = "video_path"
        if not candidates and keys:
            lab_key = _key_of(row, keys, spec.aliases)
            if lab_key is not None:
                candidates = [ai for ai, ak in app_keys.items() if ak == lab_key]
                rule = "key"
        if not candidates and spec.allow_unique_basename and lab_stems[li]:
            same_lab = [k for k, s in lab_stems.items() if s == lab_stems[li]]
            same_app = [ai for ai, s in app_stems.items() if s == lab_stems[li]]
            if len(same_lab) == 1 and len(same_app) == 1:
                candidates, rule = same_app, "basename"
            elif same_app:
                result.ambiguous.append(
                    {
                        "lab": li,
                        "rule": "basename",
                        "candidates": same_app,
                        "reason": "the file name is not unique",
                    }
                )
                continue
        if len(candidates) == 1:
            claims.setdefault(candidates[0], []).append(li)
            result.rules[li] = rule
        elif len(candidates) > 1:
            result.ambiguous.append(
                {
                    "lab": li,
                    "rule": rule,
                    "candidates": candidates,
                    "reason": "several app rows fit",
                }
            )
        else:
            result.lab_unmatched.append(li)

    for ai, lab_rows in claims.items():
        if len(lab_rows) == 1:
            result.pairs.append((lab_rows[0], ai))
        else:
            for li in lab_rows:
                result.ambiguous.append(
                    {
                        "lab": li,
                        "rule": result.rules.get(li, ""),
                        "candidates": [ai],
                        "reason": "several lab rows claim the same app row",
                    }
                )
    paired_app = {ai for _li, ai in result.pairs}
    result.app_unmatched = [ai for ai in app.index if ai not in paired_app]
    result.pairs.sort()
    return result


def _closest_paths(
    lab_path: tuple[str, ...], app_paths: Mapping[int, tuple[str, ...]]
) -> list[int]:
    """App rows whose path shares the LONGEST trailing run of components with ``lab_path``.

    At least two components must agree (a bare file name repeats across days), and only the
    rows at the maximum count: ``Dia_2/CECT_4/CECT_4`` beats ``Dia_1/CECT_4/CECT_4`` (three
    shared components against two); a tie stays a tie, so it is reported as ambiguous.
    """
    best = 0
    found: list[int] = []
    for index, parts in app_paths.items():
        shared = 0
        for a, b in zip(reversed(lab_path), reversed(parts), strict=False):
            if a != b:
                break
            shared += 1
        if shared < 2 or shared < best:
            continue
        if shared > best:
            best, found = shared, []
        found.append(index)
    return found


def build_pair_table(
    lab: pd.DataFrame, app: pd.DataFrame, pairs: Sequence[tuple[int, int]]
) -> pd.DataFrame:
    """Matched rows side by side: ``lab_*`` and ``app_*`` columns plus the row identity."""
    if not pairs:
        return pd.DataFrame(columns=["lab_index", "app_index"])
    lab_rows = [li for li, _ in pairs]
    app_rows = [ai for _, ai in pairs]
    left = lab.loc[lab_rows].add_prefix("lab_").reset_index(drop=True)
    right = app.loc[app_rows].add_prefix("app_").reset_index(drop=True)
    table = pd.concat([left, right], axis=1)
    table.insert(0, "app_index", app_rows)
    table.insert(0, "lab_index", lab_rows)
    return table


def match_summary(lab: pd.DataFrame, app: pd.DataFrame, result: MatchResult) -> dict[str, Any]:
    """Counts and the unmatched/ambiguous rows of one sheet, ready for the report."""

    def lab_view(i: int) -> dict[str, Any]:
        row = lab.loc[i]
        return {
            "sheet_row": int(row["source_row"]),
            **{k: _plain(row.get(k)) for k in _IDENTITY_FIELDS if k in lab.columns},
        }

    def app_view(i: int) -> dict[str, Any]:
        row = app.loc[i]
        return {
            k: _plain(row.get(k))
            for k in ("group", "day", "subject", "experiment_id", "video_path")
        }

    return {
        "lab_rows": len(lab),
        "app_rows": len(app),
        "matched": len(result.pairs),
        "by_rule": {
            rule: sum(1 for r in result.rules.values() if r == rule)
            for rule in sorted(set(result.rules.values()))
        },
        "lab_unmatched": [lab_view(i) for i in result.lab_unmatched],
        "app_unmatched": [app_view(i) for i in result.app_unmatched],
        "ambiguous": [
            {
                **lab_view(item["lab"]),
                "rule": item["rule"],
                "reason": item["reason"],
                "candidates": [app_view(c) for c in item["candidates"]],
            }
            for item in result.ambiguous
        ],
    }


def _plain(value: Any) -> Any:
    return None if _is_missing(value) else jsonable(value)


# =============================================================================
# Comparison of one sheet
# =============================================================================


def compare_sheet(name: str, pairs: pd.DataFrame) -> dict[str, Any]:
    """Statistics of one lab sheet's matched pairs (see the module docstring for the rules)."""
    block: dict[str, Any] = {"pairs": len(pairs)}
    if pairs.empty:
        return block

    def col(prefix: str, field_name: str) -> pd.Series:
        return pairs[f"{prefix}_{field_name}"]

    def has(prefix: str, field_name: str) -> bool:
        return f"{prefix}_{field_name}" in pairs.columns

    if name == "latencies":
        for event in ("encounter", "entry"):
            lat = f"{event}_latency_s"
            if has("lab", lat):
                block[event] = latency_comparison(
                    col("app", lat),
                    col("app", f"{event}_censored"),
                    col("lab", lat),
                    col("lab", f"{event}_censored"),
                )
        for errors in ("primary_errors", "total_errors"):
            if has("lab", errors):
                block[errors] = count_block(
                    col("app", errors).to_numpy(dtype=float),
                    col("lab", errors).to_numpy(dtype=float),
                )
    elif name == "strategy":
        if has("lab", "strategy"):
            block["strategy"] = _strategy_block(pairs)
    elif name == "probe":
        if has("lab", "probe_score"):
            block["score"] = count_block(
                col("app", "probe_first_hole_score").to_numpy(dtype=float),
                col("lab", "probe_score").to_numpy(dtype=float),
            )
        if has("lab", "attempts"):
            block["attempts"] = count_block(
                col("app", "probe_attempts_to_target").to_numpy(dtype=float),
                col("lab", "attempts").to_numpy(dtype=float),
            )
        if has("lab", "first_error_latency_s"):
            block["first_error_latency"] = _first_error_block(pairs)
    if has("lab", "start_time_s"):
        block["start_offset"] = asdict(
            start_offset_distribution(
                col("app", "t_start_s").to_numpy(dtype=float),
                col("lab", "start_time_s").to_numpy(dtype=float),
            )
        )
    return block


def _strategy_block(pairs: pd.DataFrame) -> dict[str, Any]:
    lab = pairs["lab_strategy"]
    app = pairs["app_strategy_auto"]
    usable = lab.notna() & app.notna()
    kappa = cohen_kappa(app[usable].tolist(), lab[usable].tolist())
    return {
        "counts": {
            "pairs": len(pairs),
            "lab_missing": int(lab.isna().sum()),
            "app_missing": int((lab.notna() & app.isna()).sum()),
            "compared": int(usable.sum()),
        },
        "kappa": asdict(kappa),
    }


def _first_error_block(pairs: pd.DataFrame) -> dict[str, Any]:
    lab = pd.to_numeric(pairs["lab_first_error_latency_s"], errors="coerce")
    app = pd.to_numeric(pairs["app_probe_first_error_latency_s"], errors="coerce")
    return {
        "missing": {
            "both_present": int((lab.notna() & app.notna()).sum()),
            "both_blank": int((lab.isna() & app.isna()).sum()),
            "lab_only": int((lab.notna() & app.isna()).sum()),
            "app_only": int((lab.isna() & app.notna()).sum()),
        },
        "agreement": agreement_block(app.to_numpy(dtype=float), lab.to_numpy(dtype=float)),
    }


# =============================================================================
# Validation run (lab sheets x app table)
# =============================================================================


@dataclass
class ValidationResult:
    """Everything a run produced: a JSON-able summary plus the row-level tables."""

    summary: dict[str, Any]
    pair_tables: dict[str, pd.DataFrame]
    notes: list[str] = field(default_factory=list)


def load_lab_tables(mapping: ValidationMapping) -> tuple[dict[str, pd.DataFrame], list[str]]:
    """Read every mapped lab sheet; ``notes`` collects cells that could not be read."""
    tables: dict[str, pd.DataFrame] = {}
    notes: list[str] = []
    for name, spec in mapping.sheets.items():
        tables[name], sheet_notes = read_lab_sheet(spec)
        notes.extend(sheet_notes)
    return tables, notes


def match_all(
    lab_tables: Mapping[str, pd.DataFrame], app: pd.DataFrame, spec: MatchSpec
) -> dict[str, MatchResult]:
    """Match each lab sheet independently with the app rows."""
    return {name: match_rows(table, app, spec) for name, table in lab_tables.items()}


def evaluate(
    lab_tables: Mapping[str, pd.DataFrame],
    app: pd.DataFrame,
    matches: Mapping[str, MatchResult],
    *,
    only_app_rows: Iterable[int] | None = None,
) -> ValidationResult:
    """Compare every matched sheet; ``only_app_rows`` restricts to a subset of app rows."""
    keep = None if only_app_rows is None else set(only_app_rows)
    summary: dict[str, Any] = {}
    pair_tables: dict[str, pd.DataFrame] = {}
    for name, table in lab_tables.items():
        result = matches[name]
        pairs = [(li, ai) for li, ai in result.pairs if keep is None or ai in keep]
        pair_table = build_pair_table(table, app, pairs)
        pair_tables[name] = pair_table
        block = compare_sheet(name, pair_table)
        if keep is None:
            block["matching"] = match_summary(table, app, result)
        else:
            block["matching"] = {"lab_rows": len(table), "matched": len(pairs)}
        if not pair_table.empty and "app_status" in pair_table.columns:
            statuses = pair_table["app_status"].fillna("missing").value_counts()
            block["app_status"] = {str(k): int(v) for k, v in statuses.items()}
        summary[name] = block
    return ValidationResult(summary=summary, pair_tables=pair_tables)


# =============================================================================
# Recompute (analysis only, through the real public entry)
# =============================================================================

# Parameter groups of the calibration, in the order they are optimised (a later group may
# depend on an earlier one: errors depend on the visits and on where the trial ends).
PARAM_GROUPS: Final[dict[str, tuple[str, ...]]] = {
    "visits": ("visit_min_cover", "visit_enter_frames", "visit_exit_frames"),
    "entry": (
        "entry_min_cover",
        "entry_max_visible_fraction",
        "entry_hold_s",
        "entry_absent_s",
    ),
    "strategy": (
        "center_radius_ratio",
        "strategy_direct_max_errors",
        "strategy_serial_min_adjacent_fraction",
        "strategy_serial_max_center_crossings",
        "strategy_adjacent_max_step",
    ),
}

#: Candidate values per parameter (the default grid; ``--grid`` replaces entries). The
#: current default of each parameter is included so "no change" is always a candidate.
DEFAULT_GRID: Final[dict[str, list[float | int]]] = {
    "visit_min_cover": [0.2, 0.3, 0.4, 0.5],
    "visit_enter_frames": [1, 2, 3],
    "visit_exit_frames": [2, 3, 5],
    "entry_min_cover": [0.4, 0.5, 0.65],
    "entry_max_visible_fraction": [0.25, 0.35, 0.5],
    "entry_hold_s": [0.3, 0.5, 1.0],
    "entry_absent_s": [2.0, 3.0, 5.0],
    "center_radius_ratio": [0.4, 0.5, 0.6],
    "strategy_direct_max_errors": [2, 3, 4],
    "strategy_serial_min_adjacent_fraction": [0.5, 2.0 / 3.0, 0.8],
    "strategy_serial_max_center_crossings": [0, 1, 2],
    "strategy_adjacent_max_step": [2],
}

_PRESET_KEYS: Final = (
    "entry_min_cover",
    "entry_max_visible_fraction",
    "entry_hold_s",
    "entry_absent_s",
    "entry_min_reference_frames",
)


@dataclass(frozen=True)
class CaseFiles:
    """The result files of one analysed video."""

    base: str
    trajectory: Path
    arena: Path | None
    rois: Path | None
    group: str | None
    day: str | None
    subject: str | None


def discover_cases(root: str | Path) -> tuple[list[CaseFiles], list[str]]:
    """Find every ``3_CoordMovimento_<base>.parquet`` below ``root`` and its zone files.

    Group/day/subject come from the ``Grupo_*/Dia_*/Sujeito_*`` folders the app writes.
    Multi-aquarium trajectories (``*_aquarium_N``) are skipped with a note.
    """
    base_dir = Path(root)
    if not base_dir.is_dir():
        raise ValidationInputError(f"results folder not found: {base_dir}")
    cases: list[CaseFiles] = []
    notes: list[str] = []
    for trajectory in sorted(base_dir.rglob(f"{_TRAJECTORY_PREFIX}*.parquet")):
        base = trajectory.name[len(_TRAJECTORY_PREFIX) : -len(".parquet")]
        if re.search(r"_aquarium_\d+$", base):
            notes.append(f"{trajectory}: multi-aquarium trajectory skipped (Barnes is one arena)")
            continue
        arena = trajectory.with_name(f"{_ARENA_PREFIX}{base}.parquet")
        rois = trajectory.with_name(f"{_ROIS_PREFIX}{base}.parquet")
        identity: dict[str, str | None] = {"group": None, "day": None, "subject": None}
        for part in trajectory.parent.relative_to(base_dir).parts:
            for field_name, pattern in _FOLDER_RE.items():
                match = pattern.match(part)
                if match and identity[field_name] is None:
                    identity[field_name] = normalize_token(match.group(1))
        cases.append(
            CaseFiles(
                base=base,
                trajectory=trajectory,
                arena=arena if arena.is_file() else None,
                rois=rois if rois.is_file() else None,
                **identity,
            )
        )
    return cases, notes


def preset_kwargs(params: Mapping[str, Any], *, k_frames: int = 5) -> dict[str, Any]:
    """``barnes_maze_preset_v2`` keyword arguments from effective ``BarnesParams`` values."""
    kwargs: dict[str, Any] = {"k_frames": k_frames, "max_s": float(params["max_trial_s"])}
    for key in _PRESET_KEYS:
        kwargs[key] = params[key]
    return kwargs


class CaseRunner(Protocol):
    """What :func:`calibrate` needs from a recomputer (so it can be tested without the app)."""

    notes: list[str]

    @property
    def base_params(self) -> dict[str, Any]: ...

    def identity_table(self) -> pd.DataFrame: ...

    def run_case(
        self, index: int, overrides: Mapping[str, Any] | None = None
    ) -> dict[str, Any]: ...


class Recomputer:
    """Re-runs the analysis (never detection) of existing results with ``BarnesParams`` overrides.

    Each trajectory is analysed through ``AnalysisService.run_full_analysis`` exactly as the
    individual report does: arena-local pixels, the report's pixel/cm rule, the analysis
    window resolved by ``AnalysisWindowService``. Trajectories and sidecars are COPIED to a
    private temporary folder first, so the window artifact (``7_AnalysisWindow_*``) the
    resolver writes never touches the user's results.

    Args:
        cases: Result files to analyse.
        project_data: ``project_config.json`` of the project (calibration, behavioural
            config, analysis parameters, video entries); ``{}`` uses the app's defaults.
        window_mode: ``"preset_v2"`` rebuilds the window with ``barnes_maze_preset_v2`` and
            the effective entry thresholds (what calibrating them needs); ``"project"``
            keeps the window the project declares; ``"none"`` analyses the whole recording.
        k_frames: START persistence of the rebuilt window (the preset's default).
        table_diameter_cm: Overrides the pixel/cm fallback (table diameter).
        trial_type: Default trial type; ``probe_regex`` marks probe videos by their path.
    """

    def __init__(
        self,
        cases: Sequence[CaseFiles],
        *,
        project_data: Mapping[str, Any] | None = None,
        window_mode: str = "preset_v2",
        k_frames: int = 5,
        table_diameter_cm: float | None = None,
        trial_type: str = "training",
        probe_regex: str | None = None,
        settings_obj: Any = None,
    ) -> None:
        if window_mode not in ("preset_v2", "project", "none"):
            raise ValidationInputError(f"unknown window mode '{window_mode}'")
        from zebtrack.analysis.analysis_service import AnalysisService
        from zebtrack.core.services.experiment_profile import resolve_experiment_profile
        from zebtrack.settings import load_settings

        self._cases = list(cases)
        self._project: dict[str, Any] = dict(project_data or {})
        self._window_mode = window_mode
        self._k_frames = k_frames
        self._table_diameter_cm = table_diameter_cm
        self._trial_type = trial_type
        self._probe_re = re.compile(probe_regex, re.IGNORECASE) if probe_regex else None
        self._settings = settings_obj if settings_obj is not None else load_settings()
        self._service = AnalysisService(settings_obj=self._settings)
        self._analysis: dict[str, Any] = self._service.collect_analysis_parameters(self._project)
        profile = resolve_experiment_profile(project_data=self._project)
        self._base_params: dict[str, Any] = dict(profile.protocol_params)
        self._workdir = Path(tempfile.mkdtemp(prefix="barnes_validation_"))
        self._prepared: dict[int, dict[str, Any]] = {}
        self.notes: list[str] = []

    # -- lifecycle ---------------------------------------------------------------

    def close(self) -> None:
        """Delete the private copies."""
        shutil.rmtree(self._workdir, ignore_errors=True)

    def __enter__(self) -> Recomputer:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # -- public API --------------------------------------------------------------

    @property
    def base_params(self) -> dict[str, Any]:
        """The project's own ``protocol_params.barnes`` block (the starting point)."""
        return dict(self._base_params)

    def identity_table(self) -> pd.DataFrame:
        """One identity-only app row per case (group/day/subject/experiment/video path)."""
        rows = []
        for case in self._cases:
            entry = self._project_entry(case)
            rows.append(
                {
                    **{column: None for column in APP_COLUMNS},
                    **{column: math.nan for column in _APP_NUMERIC},
                    "group": case.group,
                    "day": case.day,
                    "subject": case.subject,
                    "experiment_id": case.base,
                    "video_path": (entry or {}).get("path"),
                }
            )
        return coerce_app_frame(pd.DataFrame(rows, columns=list(APP_COLUMNS)))

    def run_case(self, index: int, overrides: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Analyse one case with ``overrides`` on top of the project's Barnes params."""
        case = self._cases[index]
        prepared = self._prepare(index)
        params = {**self._base_params, **dict(overrides or {})}
        effective = self._effective_params(params)
        analysis = self._analysis
        behavioral = dict(analysis.get("behavioral_config") or {})
        behavioral.update(
            {"protocol": "barnes", "animal_model": "rodent", "protocol_params": {"barnes": params}}
        )
        window = self._window(prepared, effective)
        inputs = {"barnes": {"trial_type": self._trial_type_of(case)}}
        report, *_rest = self._service.run_full_analysis(
            trajectory_df=prepared["df"],
            pixelcm_x=prepared["px"],
            pixelcm_y=prepared["py"],
            video_height_px=int(prepared["height"]),
            arena_polygon_px=prepared["arena"],
            rois=prepared["rois"],
            fps=prepared["fps"],
            freezing_vel_threshold=analysis.get("freezing_vel_threshold", 1.0),
            freezing_min_duration=analysis.get("freezing_min_duration", 1.0),
            smoothing_window_length=analysis.get("smoothing_window_length"),
            smoothing_polyorder=analysis.get("smoothing_polyorder"),
            behavioral_config=behavioral,
            window=window,
            protocol_inputs=inputs,
        )
        start = None if window is None or window.start is None else window.start.t_s
        row = metrics_row(report["protocol_metrics"], window_start_s=start)
        row.update(group=case.group, day=case.day, subject=case.subject, experiment_id=case.base)
        return row

    def run_all(
        self, overrides: Mapping[str, Any] | None = None, indexes: Iterable[int] | None = None
    ) -> pd.DataFrame:
        """Analyse several cases; rows keep the cases' positions as their index."""
        selected = list(range(len(self._cases)) if indexes is None else indexes)
        rows = {i: self.run_case(i, overrides) for i in selected}
        frame = pd.DataFrame.from_dict(rows, orient="index", columns=list(APP_COLUMNS))
        frame["video_path"] = self.identity_table().loc[frame.index, "video_path"]
        return coerce_app_frame(frame.reset_index(drop=True)).set_axis(frame.index)

    # -- internals ---------------------------------------------------------------

    def _effective_params(self, params: Mapping[str, Any]) -> dict[str, Any]:
        from zebtrack.analysis.protocols.barnes.contract import parse_barnes_params

        parsed, warnings = parse_barnes_params(params)
        for warning in warnings:
            if warning not in self.notes:
                self.notes.append(warning)
        return parsed.model_dump(mode="python")

    def _trial_type_of(self, case: CaseFiles) -> str:
        entry = self._project_entry(case)
        declared = ((entry or {}).get("protocol_inputs") or {}).get("barnes", {}).get("trial_type")
        if declared in ("training", "probe"):
            return str(declared)
        if self._probe_re is not None and self._probe_re.search(str(case.trajectory)):
            return "probe"
        return self._trial_type

    def _project_entry(self, case: CaseFiles) -> dict[str, Any] | None:
        """The project's video entry of ``case``: same experiment id, narrowed by identity."""
        entries = [
            video
            for batch in self._project.get("batches", []) or []
            for video in batch.get("videos", []) or []
            if (video.get("experiment_id") or Path(str(video.get("path", ""))).stem) == case.base
        ]
        if len(entries) > 1:
            wanted = (case.group, case.day, case.subject)
            entries = [
                e
                for e in entries
                if tuple(
                    normalize_token((e.get("metadata") or {}).get(k))
                    for k in ("group", "day", "subject")
                )
                == wanted
            ]
        return entries[0] if len(entries) == 1 else None

    def _prepare(self, index: int) -> dict[str, Any]:
        """Load once, in the arena's local pixel space, exactly as the report does."""
        if index in self._prepared:
            return self._prepared[index]
        import math as _math

        from zebtrack.analysis.roi_builder import build_roi_from_polygon
        from zebtrack.analysis.time_base import resolve_time_base
        from zebtrack.core.project.zone_manager import ZoneManager
        from zebtrack.io.object_sidecar import trajectory_sidecars

        case = self._cases[index]
        folder = self._workdir / f"case_{index}"
        folder.mkdir(parents=True, exist_ok=True)
        copy = folder / case.trajectory.name
        shutil.copy2(case.trajectory, copy)
        for sidecar in trajectory_sidecars(case.trajectory):
            if not sidecar.name.startswith("7_"):
                shutil.copy2(sidecar, folder / sidecar.name)
        df = pd.read_parquet(copy)
        zones = ZoneManager.load_zones_from_parquet(
            {
                "parquet_files": {
                    "arena": str(case.arena) if case.arena else None,
                    "rois": str(case.rois) if case.rois else None,
                }
            }
        )
        if zones is None or not zones.roi_polygons:
            raise ValidationInputError(
                f"{case.base}: no zones (1_ProcessingArea/2_AreasOfInterest)"
            )
        polygon = [(float(x), float(y)) for x, y in (zones.polygon or [])]
        if not polygon:
            raise ValidationInputError(f"{case.base}: the arena polygon is missing")
        xs, ys = [p[0] for p in polygon], [p[1] for p in polygon]
        off_x, off_y = _math.floor(min(xs)), _math.floor(min(ys))
        width = max(_math.ceil(max(xs)) - off_x, 1)
        height = max(_math.ceil(max(ys)) - off_y, 1)
        rois = [
            roi
            for roi in (
                build_roi_from_polygon(
                    name, [(float(px) - off_x, float(py) - off_y) for px, py in poly]
                )
                for name, poly in zip(zones.roi_names, zones.roi_polygons, strict=False)
            )
            if roi is not None
        ]
        local = self._to_local(df, off_x, off_y, width, height)
        settings_fps = float(self._settings.video_processing.fps)
        time_base = resolve_time_base(df, fallback_fps=settings_fps)
        px, py = self._pixel_cm(width, height)
        prepared = {
            "df": local,
            "path": copy,
            "rois": rois,
            "arena": [(x - off_x, y - off_y) for x, y in polygon],
            "height": height,
            "px": px,
            "py": py,
            "fps": float(time_base.fps_video or settings_fps),
            "time_base": time_base,
        }
        self._prepared[index] = prepared
        return prepared

    @staticmethod
    def _to_local(
        df: pd.DataFrame, off_x: float, off_y: float, width: float, height: float
    ) -> pd.DataFrame:
        """The arena-local space of ``ReportGenerationCoordinator._normalize_df_to_local_space``."""
        if off_x == 0 and off_y == 0:
            return df.copy()
        local = df.drop(
            columns=[c for c in ("x_cm", "y_cm", "x_center_cm", "y_center_cm") if c in df.columns]
        )
        for column in ("x_center_px", "x1", "x2"):
            if column in local.columns:
                local[column] = (local[column] - off_x).clip(lower=0, upper=width)
        for column in ("y_center_px", "y1", "y2"):
            if column in local.columns:
                local[column] = (local[column] - off_y).clip(lower=0, upper=height)
        return local

    def _pixel_cm(self, width: float, height: float) -> tuple[float, float]:
        """The report's rule (``_resolve_pixel_cm``), falling back to the table diameter."""
        calibration = self._project.get("calibration") or {}
        w_cm = (
            calibration.get("aquarium_width_cm")
            or self._table_diameter_cm
            or self._base_params.get("table_diameter_cm", 184.0)
        )
        h_cm = (
            calibration.get("aquarium_height_cm")
            or self._table_diameter_cm
            or self._base_params.get("table_diameter_cm", 184.0)
        )
        px_x = float(calibration.get("pixel_per_cm_x", 1.0))
        px_y = float(calibration.get("pixel_per_cm_y", 1.0))
        if self._table_diameter_cm is not None:
            return width / float(self._table_diameter_cm), height / float(self._table_diameter_cm)
        return (
            px_x if px_x > 1.0 else (width / float(w_cm) if w_cm and width > 0 else 1.0),
            px_y if px_y > 1.0 else (height / float(h_cm) if h_cm and height > 0 else 1.0),
        )

    def _window(self, prepared: Mapping[str, Any], effective: Mapping[str, Any]) -> Any:
        if self._window_mode == "none":
            return None
        from zebtrack.analysis.analysis_window_service import (
            AnalysisWindowService,
            project_subject_names,
            resolve_window_spec,
        )
        from zebtrack.analysis.track_significance import min_track_duration_from
        from zebtrack.core.conditions.presets import barnes_maze_preset_v2

        spec = (
            barnes_maze_preset_v2(**preset_kwargs(effective, k_frames=self._k_frames))
            if self._window_mode == "preset_v2"
            else resolve_window_spec(self._project)
        )
        if spec is None:
            return None
        return AnalysisWindowService(
            roi_rule=self._service.resolve_roi_rule(),
            min_track_duration_s=min_track_duration_from(self._settings),
        ).resolve(
            prepared["path"],
            spec,
            trajectory_df=prepared["df"],
            rois=prepared["rois"],
            subject_names=project_subject_names(self._project),
            pixelcm=(prepared["px"], prepared["py"]),
        )


# =============================================================================
# Calibration
# =============================================================================

#: Smoothing constants of the relative loss: a metric whose reference value is 0 would make
#: any ratio explode, so ``(m + eps) / (m0 + eps)`` is used (eps in the metric's own unit).
_LOSS_EPS: Final[dict[str, float]] = {
    "mad_encounter": 0.5,
    "mad_entry": 0.5,
    "entry_censoring_mismatch": 0.5,
    "mad_primary_errors": 0.05,
    "mad_total_errors": 0.05,
    "mad_probe_score": 0.05,
    "mad_attempts": 0.05,
    "mad_first_error": 0.5,
    "strategy_disagreement": 0.02,
}


def _get(block: Mapping[str, Any], *path: str) -> float:
    node: Any = block
    for step in path:
        if not isinstance(node, Mapping) or step not in node:
            return _NAN
        node = node[step]
    return float(node) if isinstance(node, int | float) and node is not None else _NAN


def group_losses(group: str, summary: Mapping[str, Any]) -> dict[str, float]:
    """The lower-is-better values a parameter group is judged on, from an evaluation summary.

    * ``visits``: MAD of encounter latency (both observed), primary and total errors, and the
      probe score / attempts / first-error latency, whichever the lab sheets provide;
    * ``entry``: MAD of entry latency (both observed) and the number of pairs the two sides
      disagree on being censored;
    * ``strategy``: share of pairs whose automatic strategy differs from the lab's.
    """
    lat = summary.get("latencies", {})
    probe = summary.get("probe", {})
    values: dict[str, float] = {}
    if group == "visits":
        values["mad_encounter"] = _get(lat, "encounter", "observed", "mad")
        values["mad_primary_errors"] = _get(lat, "primary_errors", "mad")
        values["mad_total_errors"] = _get(lat, "total_errors", "mad")
        values["mad_probe_score"] = _get(probe, "score", "mad")
        values["mad_attempts"] = _get(probe, "attempts", "mad")
        values["mad_first_error"] = _get(probe, "first_error_latency", "agreement", "mad")
    elif group == "entry":
        values["mad_entry"] = _get(lat, "entry", "observed", "mad")
        cens = lat.get("entry", {}).get("censoring", {})
        if cens.get("n"):
            values["entry_censoring_mismatch"] = float(
                cens.get("lab_only_censored", 0) + cens.get("app_only_censored", 0)
            )
    elif group == "strategy":
        kappa = summary.get("strategy", {}).get("strategy", {}).get("kappa", {})
        agreement = kappa.get("observed_agreement")
        if isinstance(agreement, int | float) and math.isfinite(agreement):
            values["strategy_disagreement"] = 1.0 - float(agreement)
    return {k: v for k, v in values.items() if math.isfinite(v)}


def relative_loss(values: Mapping[str, float], reference: Mapping[str, float]) -> float:
    """Mean of ``(m + eps) / (m_ref + eps)`` over the metrics both have; < 1 beats the reference.

    Scale-free on purpose: latency seconds, error counts and a disagreement rate cannot be
    summed, but "how much worse or better than where we started" can be averaged.
    """
    ratios = [
        (values[name] + _LOSS_EPS[name]) / (reference[name] + _LOSS_EPS[name])
        for name in values
        if name in reference
    ]
    return float(np.mean(ratios)) if ratios else math.inf


def split_cases(
    identities: pd.DataFrame, indexes: Sequence[int], *, fraction: float, seed: int
) -> tuple[list[int], list[int]]:
    """Seeded calibration / held-out split, stratified by group x day when they exist.

    Each stratum is shuffled with the seed and cut at ``round(fraction · size)`` (at least
    one case on each side when the stratum has two or more). Strata of a single case are
    pooled, shuffled and cut the same way, so the overall ratio holds.
    """
    if not 0.0 < fraction < 1.0:
        raise ValidationInputError("--calibration-fraction must be between 0 and 1")
    rng = np.random.default_rng(seed)
    strata: dict[tuple[str, str], list[int]] = {}
    for index in sorted(indexes):
        row = identities.loc[index]
        strata.setdefault((str(row.get("group")), str(row.get("day"))), []).append(index)
    calibration: list[int] = []
    held_out: list[int] = []
    singles: list[int] = []
    for members in strata.values():
        if len(members) == 1:
            singles.extend(members)
            continue
        shuffled = list(rng.permutation(members))
        cut = min(max(round(fraction * len(shuffled)), 1), len(shuffled) - 1)
        calibration.extend(int(i) for i in shuffled[:cut])
        held_out.extend(int(i) for i in shuffled[cut:])
    if singles:
        shuffled = list(rng.permutation(singles))
        cut = round(fraction * len(shuffled))
        calibration.extend(int(i) for i in shuffled[:cut])
        held_out.extend(int(i) for i in shuffled[cut:])
    return sorted(calibration), sorted(held_out)


def grid_candidates(
    grid: Mapping[str, Sequence[float | int]], keys: Sequence[str]
) -> list[dict[str, float | int]]:
    """Cartesian product of the grid values of ``keys`` (a key absent from the grid is fixed)."""
    axes = [list(grid[key]) for key in keys if grid.get(key)]
    names = [key for key in keys if grid.get(key)]
    return [dict(zip(names, combo, strict=True)) for combo in product(*axes)] if names else [{}]


def _distance_to_defaults(candidate: Mapping[str, Any], defaults: Mapping[str, Any]) -> float:
    """Tie-break: how far a candidate is from the current values (relative, summed)."""
    total = 0.0
    for key, value in candidate.items():
        base = defaults.get(key)
        if isinstance(base, int | float) and isinstance(value, int | float):
            total += abs(float(value) - float(base)) / (abs(float(base)) or 1.0)
    return total


@dataclass
class CalibrationOutcome:
    """What a calibration found."""

    chosen: dict[str, Any]
    suggested_block: dict[str, Any]
    groups: dict[str, dict[str, Any]]
    calibration_cases: list[int]
    held_out_cases: list[int]
    default_params: dict[str, Any]
    held_out_default: dict[str, Any]
    held_out_calibrated: dict[str, Any]
    calibration_default: dict[str, Any]
    calibration_calibrated: dict[str, Any]
    held_out_verdict: dict[str, Any]


def calibrate(
    recomputer: CaseRunner,
    lab_tables: Mapping[str, pd.DataFrame],
    match_spec: MatchSpec,
    *,
    grid: Mapping[str, Sequence[float | int]],
    seed: int = 1,
    calibration_fraction: float = 0.6,
    max_candidates: int = 500,
    groups: Sequence[str] = tuple(PARAM_GROUPS),
) -> CalibrationOutcome:
    """Grid-search the Barnes thresholds on a calibration subset; judge them on the rest.

    The groups of :data:`PARAM_GROUPS` are optimised in order, each over the Cartesian product
    of its own grid with the earlier groups fixed at their chosen values; the loss of a
    candidate is :func:`relative_loss` against the group's starting point. The best candidate
    wins; ties go to the one closest to the current values ("do not move without evidence").
    A group whose lab data is absent is skipped. Nothing is written to the project.
    """
    unknown = sorted(k for k in grid if k not in {p for g in PARAM_GROUPS.values() for p in g})
    if unknown:
        raise ValidationInputError(f"the grid has parameters that cannot be calibrated: {unknown}")
    identities = recomputer.identity_table()
    matches = match_all(lab_tables, identities, match_spec)
    matched = sorted({ai for m in matches.values() for _li, ai in m.pairs})
    if len(matched) < 4:
        raise ValidationInputError(
            f"only {len(matched)} video(s) match the lab sheets; calibration needs at least 4"
        )
    calibration_cases, held_out_cases = split_cases(
        identities, matched, fraction=calibration_fraction, seed=seed
    )
    logger.info(
        "barnes_validation.calibrate.split",
        calibration=len(calibration_cases),
        held_out=len(held_out_cases),
        seed=seed,
    )

    cache: dict[tuple[int, tuple[tuple[str, Any], ...]], dict[str, Any]] = {}

    def frame_for(params: Mapping[str, Any], indexes: Sequence[int]) -> pd.DataFrame:
        key_params = tuple(sorted(params.items()))
        rows = {}
        for i in indexes:
            if (i, key_params) not in cache:
                cache[(i, key_params)] = recomputer.run_case(i, params)
            rows[i] = cache[(i, key_params)]
        frame = pd.DataFrame.from_dict(rows, orient="index", columns=list(APP_COLUMNS))
        frame["video_path"] = identities.loc[frame.index, "video_path"]
        return coerce_app_frame(frame.reset_index()).set_index(frame.index)

    def summarise(params: Mapping[str, Any], indexes: Sequence[int]) -> dict[str, Any]:
        app = identities.copy()
        computed = frame_for(params, indexes)
        for column in APP_COLUMNS:
            app[column] = app[column].astype(object)
            app.loc[computed.index, column] = computed[column].astype(object)
        app = coerce_app_frame(app)
        return evaluate(lab_tables, app, matches, only_app_rows=indexes).summary

    defaults = recomputer.base_params
    current: dict[str, Any] = {}
    outcome_groups: dict[str, dict[str, Any]] = {}
    for group in groups:
        keys = PARAM_GROUPS[group]
        candidates = grid_candidates(grid, keys)
        if len(candidates) > max_candidates:
            raise ValidationInputError(
                f"group '{group}' has {len(candidates)} candidates (> {max_candidates}); "
                "shrink the grid or raise --max-candidates"
            )
        start_summary = summarise({**defaults, **current}, calibration_cases)
        reference = group_losses(group, start_summary)
        if not reference:
            outcome_groups[group] = {
                "status": "skipped",
                "reason": "the lab sheets have no data this group is judged on",
            }
            continue
        scored: list[tuple[float, float, dict[str, Any], dict[str, float]]] = []
        for number, candidate in enumerate(candidates, start=1):
            summary = summarise({**defaults, **current, **candidate}, calibration_cases)
            values = group_losses(group, summary)
            loss = relative_loss(values, reference)
            scored.append(
                (loss, _distance_to_defaults(candidate, {**defaults, **current}), candidate, values)
            )
            logger.info(
                "barnes_validation.calibrate.candidate",
                group=group,
                n=number,
                of=len(candidates),
                loss=round(loss, 4),
            )
        scored.sort(key=lambda item: (item[0], item[1]))
        best_loss, _distance, best, best_values = scored[0]
        current.update(best)
        outcome_groups[group] = {
            "status": "searched",
            "candidates": len(candidates),
            "reference_metrics": reference,
            "chosen": best,
            "chosen_metrics": best_values,
            "chosen_relative_loss": best_loss,
            "top": [
                {"params": cand, "relative_loss": loss, "metrics": vals}
                for loss, _d, cand, vals in scored[:5]
            ],
        }

    changed = {k: v for k, v in current.items() if defaults.get(k) != v}
    held_default = summarise(defaults, held_out_cases) if held_out_cases else {}
    held_chosen = summarise({**defaults, **current}, held_out_cases) if held_out_cases else {}
    cal_default = summarise(defaults, calibration_cases)
    cal_chosen = summarise({**defaults, **current}, calibration_cases)
    verdict = _held_out_verdict(
        held_default,
        held_chosen,
        groups=[g for g, info in outcome_groups.items() if info["status"] == "searched"],
    )
    return CalibrationOutcome(
        chosen=dict(current),
        suggested_block={"protocol_params": {"barnes": changed}},
        groups=outcome_groups,
        calibration_cases=calibration_cases,
        held_out_cases=held_out_cases,
        default_params=dict(defaults),
        held_out_default=held_default,
        held_out_calibrated=held_chosen,
        calibration_default=cal_default,
        calibration_calibrated=cal_chosen,
        held_out_verdict=verdict,
    )


def _held_out_verdict(
    default: Mapping[str, Any], chosen: Mapping[str, Any], *, groups: Sequence[str]
) -> dict[str, Any]:
    """Whether the calibrated values beat the defaults on cases they were NOT fitted on."""
    verdict: dict[str, Any] = {}
    for group in groups:
        ref = group_losses(group, default)
        new = group_losses(group, chosen)
        loss = relative_loss(new, ref) if ref and new else math.nan
        verdict[group] = {
            "default_metrics": ref,
            "calibrated_metrics": new,
            "relative_loss": loss,
            "improves": bool(math.isfinite(loss) and loss < 1.0),
        }
    return verdict


# =============================================================================
# Output
# =============================================================================


def _fmt(value: Any, digits: int = 3) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int | np.integer):
        return str(int(value))
    if isinstance(value, float | np.floating):
        number = float(value)
        return "-" if not math.isfinite(number) else f"{number:.{digits}f}"
    return str(value)


def md_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    """A GitHub-flavoured markdown table."""
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines.extend("| " + " | ".join(_fmt(c) for c in row) + " |" for row in rows)
    return "\n".join(lines)


def _render_agreement(title: str, block: Mapping[str, Any]) -> list[str]:
    lines = [f"#### {title}"]
    counts = block.get("counts", {})
    lines.append(
        f"Pairs {counts.get('pairs', 0)}; compared {counts.get('compared', 0)} "
        f"(lab blank {counts.get('lab_missing', 0)}, app blank {counts.get('app_missing', 0)}); "
        f"**observed on both sides: {counts.get('both_observed', 0)}**."
    )
    for label, key in (
        ("Both observed (the figure to quote)", "observed"),
        (
            "Ceiling-imputed — censored pairs kept at the ceiling, NOT observations",
            "ceiling_imputed",
        ),
    ):
        part = block.get(key, {})
        ba, icc = part.get("bland_altman", {}), part.get("icc_2_1", {})
        lines.append(f"\n*{label}*\n")
        lines.append(
            md_table(
                [
                    "n",
                    "bias (app-lab) s",
                    "95 % limits s",
                    "MAD s",
                    "ICC(2,1) [95 % CI]",
                    "Spearman rho",
                ],
                [
                    [
                        part.get("n"),
                        ba.get("bias"),
                        f"{_fmt(ba.get('loa_lower'), 2)} … {_fmt(ba.get('loa_upper'), 2)}",
                        ba.get("mean_abs_diff"),
                        f"{_fmt(icc.get('icc'))} "
                        f"[{_fmt(icc.get('ci_lower'), 2)}, {_fmt(icc.get('ci_upper'), 2)}]",
                        part.get("spearman_rho"),
                    ]
                ],
            )
        )
    cens = block.get("censoring", {})
    lines.append("\n*Censoring agreement (event did not happen within the ceiling)*\n")
    lines.append(
        md_table(
            [
                "compared",
                "both observed",
                "both censored",
                "lab only censored",
                "app only censored",
                "agreement",
                "kappa",
            ],
            [
                [
                    cens.get("n"),
                    cens.get("both_observed"),
                    cens.get("both_censored"),
                    cens.get("lab_only_censored"),
                    cens.get("app_only_censored"),
                    cens.get("agreement"),
                    cens.get("kappa"),
                ]
            ],
        )
    )
    return lines


def _render_counts(title: str, block: Mapping[str, Any]) -> list[str]:
    return [
        f"#### {title}",
        "",
        md_table(
            ["n", "exact agreement", "within ±1", "MAD", "bias (app-lab)", "Spearman rho"],
            [
                [
                    block.get("n"),
                    block.get("exact_agreement"),
                    block.get("within_1"),
                    block.get("mad"),
                    block.get("bias"),
                    block.get("spearman_rho"),
                ]
            ],
        ),
    ]


def _render_strategy(block: Mapping[str, Any]) -> list[str]:
    kappa = block.get("kappa", {})
    labels = kappa.get("labels", [])
    matrix = kappa.get("matrix", [])
    counts = block.get("counts", {})
    lines = [
        "#### Search strategy (app automatic vs lab)",
        "",
        f"Compared {counts.get('compared', 0)} of {counts.get('pairs', 0)} pairs "
        f"(lab blank/unmapped {counts.get('lab_missing', 0)}, "
        f"app without strategy {counts.get('app_missing', 0)}). "
        f"Observed agreement {_fmt(kappa.get('observed_agreement'))}; "
        f"Cohen's kappa {_fmt(kappa.get('kappa'))} "
        f"[{_fmt(kappa.get('ci_lower'), 2)}, {_fmt(kappa.get('ci_upper'), 2)}].",
        "",
        "Confusion matrix (rows = lab, columns = app):",
        "",
    ]
    lines.append(
        md_table(
            ["lab \\ app", *labels], [[lab, *row] for lab, row in zip(labels, matrix, strict=False)]
        )
    )
    return lines


def _render_offset(block: Mapping[str, Any]) -> list[str]:
    return [
        "#### START offset (app START - manual START, s)",
        "",
        md_table(
            [
                "n",
                "mean",
                "median",
                "SD",
                "min",
                "max",
                "5th pct",
                "95th pct",
                "within 0.5 s",
                "within 1 s",
                "within 2 s",
            ],
            [
                [
                    block.get("n"),
                    block.get("mean"),
                    block.get("median"),
                    block.get("sd"),
                    block.get("minimum"),
                    block.get("maximum"),
                    block.get("p5"),
                    block.get("p95"),
                    block.get("within_0_5_s"),
                    block.get("within_1_s"),
                    block.get("within_2_s"),
                ]
            ],
        ),
    ]


def _render_matching(name: str, match: Mapping[str, Any]) -> list[str]:
    lines = [
        f"Lab rows {match.get('lab_rows')}, app rows {match.get('app_rows')}, "
        f"**matched {match.get('matched')}** (rules: {match.get('by_rule') or 'none'})."
    ]
    for title, key in (
        ("Lab rows with no app counterpart", "lab_unmatched"),
        ("App rows with no lab counterpart", "app_unmatched"),
        ("Ambiguous (matched to nothing)", "ambiguous"),
    ):
        items = match.get(key) or []
        if items:
            lines.append(f"\n**{title} ({len(items)}):**\n")
            lines.extend(
                f"- {json.dumps(item, ensure_ascii=False, default=str)}" for item in items[:50]
            )
            if len(items) > 50:
                lines.append(f"- … and {len(items) - 50} more (see the workbook)")
    return lines


def render_markdown(
    summary: Mapping[str, Any],
    *,
    title: str,
    notes: Sequence[str] = (),
    calibration: Mapping[str, Any] | None = None,
) -> str:
    """The human-readable report."""
    lines = [
        f"# {title}",
        "",
        f"Generated {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}. "
        "Differences are **app - lab**; censored latencies are never treated as observations "
        "(see VALIDATION.md).",
        "",
    ]
    if notes:
        lines += ["## Notes", "", *[f"- {n}" for n in notes[:100]], ""]
    for name in SHEET_NAMES:
        block = summary.get(name)
        if not block:
            continue
        lines += [f"## Sheet: {name}", ""]
        lines += _render_matching(name, block.get("matching", {}))
        if block.get("app_status"):
            lines += ["", f"App status of the matched rows: {block['app_status']}"]
        lines.append("")
        for event in ("encounter", "entry"):
            if event in block:
                lines += [*_render_agreement(f"{event.capitalize()} latency", block[event]), ""]
        for key in ("primary_errors", "total_errors"):
            if key in block:
                lines += [*_render_counts(key.replace("_", " ").capitalize(), block[key]), ""]
        if "strategy" in block:
            lines += [*_render_strategy(block["strategy"]), ""]
        if "score" in block:
            lines += [*_render_counts("Probe: score of the first hole", block["score"]), ""]
        if "attempts" in block:
            lines += [*_render_counts("Probe: attempts until the target", block["attempts"]), ""]
        if "first_error_latency" in block:
            fe = block["first_error_latency"]
            lines += [
                "#### Probe: first-error latency",
                "",
                f"Presence: {fe.get('missing')}",
                "",
                md_table(
                    ["n", "bias (app-lab) s", "95 % limits s", "MAD s", "ICC(2,1)"],
                    [
                        [
                            fe["agreement"].get("n"),
                            fe["agreement"]["bland_altman"].get("bias"),
                            f"{_fmt(fe['agreement']['bland_altman'].get('loa_lower'), 2)} … "
                            f"{_fmt(fe['agreement']['bland_altman'].get('loa_upper'), 2)}",
                            fe["agreement"].get("mad"),
                            fe["agreement"]["icc_2_1"].get("icc"),
                        ]
                    ],
                ),
                "",
            ]
        if "start_offset" in block:
            lines += [*_render_offset(block["start_offset"]), ""]
    if calibration:
        lines += _render_calibration(calibration)
    return "\n".join(lines) + "\n"


def _render_calibration(cal: Mapping[str, Any]) -> list[str]:
    lines = [
        "## Calibration",
        "",
        f"Seeded split: {len(cal['calibration_cases'])} calibration videos, "
        f"{len(cal['held_out_cases'])} held out. Loss = mean of (metric+ε)/(reference+ε); "
        "below 1 beats the starting values.",
        "",
    ]
    for group, info in cal["groups"].items():
        lines.append(f"### Group: {group}")
        if info["status"] == "skipped":
            lines += [f"Skipped: {info['reason']}", ""]
            continue
        lines += [
            f"{info['candidates']} candidates; chosen `{info['chosen']}` "
            f"(relative loss {_fmt(info['chosen_relative_loss'])} on the calibration videos).",
            "",
            md_table(
                ["rank", "parameters", "relative loss"],
                [
                    [i + 1, json.dumps(t["params"]), t["relative_loss"]]
                    for i, t in enumerate(info["top"])
                ],
            ),
            "",
        ]
    lines += ["### Held-out evaluation (videos the thresholds were NOT fitted on)", ""]
    rows = []
    for group, info in cal["held_out_verdict"].items():
        rows.append(
            [
                group,
                json.dumps(info["default_metrics"]),
                json.dumps(info["calibrated_metrics"]),
                info["relative_loss"],
                "yes" if info["improves"] else "no — keep the defaults",
            ]
        )
    lines.append(md_table(["group", "defaults", "calibrated", "relative loss", "improves"], rows))
    lines += [
        "",
        "### Suggested `protocol_params.barnes` block",
        "",
        "```yaml",
        yaml.safe_dump(jsonable(cal["suggested_block"]), sort_keys=True).rstrip(),
        "```",
        "",
        "Nothing was written to the project; paste the block into the project's behavioural "
        "config only if the held-out evaluation supports it.",
        "",
    ]
    return lines


def flatten_summary(summary: Mapping[str, Any]) -> pd.DataFrame:
    """The summary as ``sheet / metric / statistic / value`` rows (the workbook's Summary tab)."""
    rows: list[dict[str, Any]] = []

    def walk(path: tuple[str, ...], node: Any) -> None:
        if isinstance(node, Mapping):
            for key, value in node.items():
                if key in ("lab_unmatched", "app_unmatched", "ambiguous"):
                    continue
                walk((*path, str(key)), value)
        elif isinstance(node, list | tuple):
            rows.append(
                {
                    "sheet": path[0],
                    "metric": ".".join(path[1:-1]),
                    "statistic": path[-1],
                    "value": json.dumps(jsonable(node)),
                }
            )
        else:
            rows.append(
                {
                    "sheet": path[0],
                    "metric": ".".join(path[1:-1]),
                    "statistic": path[-1],
                    "value": jsonable(node),
                }
            )

    walk((), summary)
    return (
        pd.DataFrame(rows, columns=["sheet", "metric", "statistic", "value"])
        if rows
        else pd.DataFrame(columns=["sheet", "metric", "statistic", "value"])
    )


def write_outputs(
    out_dir: str | Path,
    result: ValidationResult,
    *,
    title: str,
    calibration: CalibrationOutcome | None = None,
    app_table: pd.DataFrame | None = None,
) -> dict[str, Path]:
    """Write ``report.md``, ``comparison.xlsx`` and ``summary.json`` into ``out_dir``."""
    folder = Path(out_dir)
    folder.mkdir(parents=True, exist_ok=True)
    cal_dict = None if calibration is None else jsonable(asdict(calibration))
    markdown = render_markdown(
        result.summary, title=title, notes=result.notes, calibration=cal_dict
    )
    report_path = folder / "report.md"
    report_path.write_text(markdown, encoding="utf-8")
    json_path = folder / "summary.json"
    json_path.write_text(
        json.dumps(
            {"summary": jsonable(result.summary), "calibration": cal_dict, "notes": result.notes},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    xlsx_path = folder / "comparison.xlsx"
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        flatten_summary(result.summary).to_excel(writer, sheet_name="Summary", index=False)
        for name, table in result.pair_tables.items():
            table.to_excel(writer, sheet_name=f"pairs_{name}"[:31], index=False)
            match = result.summary.get(name, {}).get("matching", {})
            unmatched = [{"side": "lab", **row} for row in match.get("lab_unmatched", [])]
            unmatched += [{"side": "app", **row} for row in match.get("app_unmatched", [])]
            unmatched += [
                {
                    "side": "ambiguous",
                    **{k: v for k, v in row.items() if k != "candidates"},
                    "candidates": json.dumps(row.get("candidates"), default=str),
                }
                for row in match.get("ambiguous", [])
            ]
            if unmatched:
                pd.DataFrame(unmatched).to_excel(
                    writer, sheet_name=f"unmatched_{name}"[:31], index=False
                )
        if app_table is not None:
            app_table.to_excel(writer, sheet_name="app_results", index=False)
        if calibration is not None:
            rows = [
                {
                    "group": g,
                    "rank": i + 1,
                    "params": json.dumps(t["params"]),
                    "relative_loss": t["relative_loss"],
                }
                for g, info in calibration.groups.items()
                if info["status"] == "searched"
                for i, t in enumerate(info["top"])
            ]
            pd.DataFrame(rows).to_excel(writer, sheet_name="calibration", index=False)
    return {"report": report_path, "workbook": xlsx_path, "summary": json_path}


# =============================================================================
# CLI
# =============================================================================


def _parse_overrides(items: Sequence[str]) -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    for item in items:
        if "=" not in item:
            raise ValidationInputError(f"--set expects key=value, got '{item}'")
        key, raw = item.split("=", 1)
        try:
            overrides[key.strip()] = json.loads(raw)
        except json.JSONDecodeError:
            overrides[key.strip()] = raw
    return overrides


def _load_grid(path: str | None) -> dict[str, list[float | int]]:
    grid = {k: list(v) for k, v in DEFAULT_GRID.items()}
    if path:
        try:
            custom = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as exc:
            raise ValidationInputError(f"cannot read the grid file {path}: {exc}") from exc
        if not isinstance(custom, Mapping):
            raise ValidationInputError("the grid file must map parameter names to lists")
        for key, values in custom.items():
            grid[str(key)] = list(values) if isinstance(values, list | tuple) else [values]
    return grid


def _load_project(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    target = Path(path)
    if target.is_dir():
        target = target / "project_config.json"
    try:
        return dict(json.loads(target.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        raise ValidationInputError(f"cannot read the project file {target}: {exc}") from exc


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="barnes_validation.py",
        description="Validate/calibrate the Barnes-maze metrics against the lab's manual scoring.",
    )
    sub = parser.add_subparsers(dest="mode", required=True)

    init = sub.add_parser("init-mapping", help="write a documented example mapping file")
    init.add_argument("--out", required=True, help="where to write the example (.yaml)")

    def common(p: argparse.ArgumentParser, *, mapping_required: bool) -> None:
        p.add_argument("--mapping", required=mapping_required, help="mapping file (.yaml/.json)")
        p.add_argument("--out", required=True, help="folder for report.md / comparison.xlsx")

    def recompute_args(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--results-root",
            required=True,
            help="folder with the 3_CoordMovimento_* results (searched recursively)",
        )
        p.add_argument("--project", help="project folder or project_config.json")
        p.add_argument(
            "--window",
            choices=("preset_v2", "project", "none"),
            default="preset_v2",
            help="analysis window: rebuild barnes_maze_preset_v2 (default), keep the "
            "project's, or none",
        )
        p.add_argument("--trial-type", choices=("training", "probe"), default="training")
        p.add_argument("--probe-regex", help="videos whose result path matches are probe trials")
        p.add_argument(
            "--table-diameter-cm",
            type=float,
            help="pixel/cm fallback when the project has no calibration",
        )

    validate = sub.add_parser("validate", help="lab sheets vs the app's unified report")
    common(validate, mapping_required=True)
    validate.add_argument(
        "--unified", required=True, help="unified*_summary_*.parquet (or the folder that holds it)"
    )

    recompute = sub.add_parser("recompute", help="re-run the analysis with BarnesParams overrides")
    common(recompute, mapping_required=False)
    recompute_args(recompute)
    recompute.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="a BarnesParams override, e.g. --set visit_min_cover=0.4",
    )

    calibrate_p = sub.add_parser("calibrate", help="grid-search thresholds, hold out the rest")
    common(calibrate_p, mapping_required=True)
    recompute_args(calibrate_p)
    calibrate_p.add_argument("--grid", help="YAML with candidate values per parameter")
    calibrate_p.add_argument("--seed", type=int, default=1)
    calibrate_p.add_argument("--calibration-fraction", type=float, default=0.6)
    calibrate_p.add_argument("--max-candidates", type=int, default=500)
    return parser


def _recomputer_from(args: argparse.Namespace) -> Recomputer:
    cases, notes = discover_cases(args.results_root)
    if not cases:
        raise ValidationInputError(f"no 3_CoordMovimento_* trajectories under {args.results_root}")
    recomputer = Recomputer(
        cases,
        project_data=_load_project(args.project),
        window_mode=args.window,
        table_diameter_cm=args.table_diameter_cm,
        trial_type=args.trial_type,
        probe_regex=args.probe_regex,
    )
    recomputer.notes.extend(notes)
    return recomputer


def run(argv: Sequence[str] | None = None) -> int:
    """CLI entry. Exit code 0 on success, 2 when an input cannot be used."""
    args = _build_parser().parse_args(argv)
    try:
        if args.mode == "init-mapping":
            target = Path(args.out)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(EXAMPLE_MAPPING, encoding="utf-8")
            print(f"wrote {target}")
            return 0
        mapping = load_mapping(args.mapping) if args.mapping else None

        if args.mode == "validate":
            assert mapping is not None
            lab_tables, notes = load_lab_tables(mapping)
            app, app_notes = read_unified(args.unified, mapping.app_columns)
            result = evaluate(lab_tables, app, match_all(lab_tables, app, mapping.match))
            result.notes = [*notes, *app_notes]
            paths = write_outputs(
                args.out, result, title="Barnes validation — unified report vs lab"
            )
        elif args.mode == "recompute":
            overrides = _parse_overrides(args.set)
            with _recomputer_from(args) as recomputer:
                app = recomputer.run_all(overrides)
                identities = recomputer.identity_table()
                app["video_path"] = identities["video_path"].to_numpy()
                notes = list(recomputer.notes)
                if mapping is None:
                    result = ValidationResult(summary={}, pair_tables={}, notes=notes)
                else:
                    lab_tables, lab_notes = load_lab_tables(mapping)
                    result = evaluate(lab_tables, app, match_all(lab_tables, app, mapping.match))
                    result.notes = [*lab_notes, *notes]
            title = f"Barnes validation — recompute {overrides or '(project params)'} vs lab"
            paths = write_outputs(args.out, result, title=title, app_table=app)
        else:
            assert mapping is not None
            lab_tables, lab_notes = load_lab_tables(mapping)
            with _recomputer_from(args) as recomputer:
                outcome = calibrate(
                    recomputer,
                    lab_tables,
                    mapping.match,
                    grid=_load_grid(args.grid),
                    seed=args.seed,
                    calibration_fraction=args.calibration_fraction,
                    max_candidates=args.max_candidates,
                )
                result = ValidationResult(
                    summary=outcome.held_out_calibrated,
                    pair_tables={},
                    notes=[*lab_notes, *recomputer.notes],
                )
            paths = write_outputs(
                args.out,
                result,
                title="Barnes calibration — held-out evaluation",
                calibration=outcome,
            )
            print(yaml.safe_dump(jsonable(outcome.suggested_block), sort_keys=True))
    except ValidationInputError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for label, path in paths.items():
        print(f"{label}: {path}")
    return 0


def main() -> None:
    """Console entry point."""
    sys.exit(run())


if __name__ == "__main__":
    main()
