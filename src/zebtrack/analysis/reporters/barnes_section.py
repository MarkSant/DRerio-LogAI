"""The Barnes-maze section of the individual Word report (#633, CONTRACTS section 8).

Reads ``report["protocol_metrics"]`` and nothing else: the metrics were computed once,
by the analysis, and every output (tidy columns, ``barnes_visits`` sheet, this section)
shows that one result. Censoring and "not measured" are written as such and are never
rendered as ``0``.

Every string goes through the reporter catalogue (``reporter.po``), resolved at call
time. The protocol tokens in the metrics (``direct``, ``training``...) are persistence
contracts and are never shown as stored: they are mapped to translated words here.
"""

from __future__ import annotations

import io
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any

import structlog
from docx.document import Document as DocxDocument
from docx.shared import Inches

from zebtrack.analysis.data_transformer import active_protocol_spec
from zebtrack.analysis.reporters.reporter_context import _

if TYPE_CHECKING:
    from zebtrack.analysis.reporters.reporter_context import ReporterContext

log = structlog.get_logger(__name__)

__all__ = ["append_barnes_section", "barnes_metrics_of", "strategy_label"]

_NOT_AVAILABLE = "N/A"


def barnes_metrics_of(ctx: ReporterContext) -> Mapping[str, Any] | None:
    """``report["protocol_metrics"]`` when this report belongs to a Barnes project.

    ``None`` for a generic project (and for any protocol that is not Barnes): the
    individual report is then byte-for-byte what it always was.
    """
    from zebtrack.analysis.protocols.barnes.contract import ASSISTANT_ID

    spec = active_protocol_spec(getattr(ctx, "behavioral_config", None))
    if spec is None or spec.zone_assistant != ASSISTANT_ID:
        return None
    metrics = (getattr(ctx, "report", None) or {}).get("protocol_metrics")
    return metrics if isinstance(metrics, Mapping) else {}


def strategy_label(strategy: str | None) -> str:
    """The translated name of a search strategy token (``None`` -> N/A)."""
    labels: dict[str, Callable[[], str]] = {
        "direct": lambda: _("Direct"),
        "serial": lambda: _("Serial"),
        "random": lambda: _("Random"),
    }
    if strategy is None:
        return _("N/A")
    label = labels.get(str(strategy))
    return label() if label is not None else str(strategy)


def _trial_label(trial_type: str | None) -> str:
    if trial_type == "probe":
        return _("Probe")
    if trial_type == "training":
        return _("Training")
    return _("N/A")


def _count(value: Any) -> str:
    """An integer metric; ``None`` (not measured) is N/A, never ``0``."""
    return _NOT_AVAILABLE if value is None else str(int(value))


def _seconds(value: float | None) -> str:
    return _NOT_AVAILABLE if value is None else f"{float(value):.2f} s"


def _centimetres(value: float | None) -> str:
    return _NOT_AVAILABLE if value is None else f"{float(value):.1f} cm"


def _latency(value: float | None, censored: bool | None) -> str:
    """A latency; a censored one is a lower bound and says so."""
    if value is None:
        return _("N/A")
    if censored:
        return _("≥ {value:.2f} s (censored)").format(value=float(value))
    return f"{float(value):.2f} s"


def _entry_text(metrics: Mapping[str, Any]) -> str:
    source = metrics.get("entry_source")
    if source == "not_applicable":
        return _("Not applicable (probe trial: there is no escape box)")
    if source == "unavailable":
        return _("Not measured (the analysis window has no burrow-entry rule)")
    return _latency(metrics.get("entry_latency_s"), metrics.get("entry_censored"))


def _strategy_text(metrics: Mapping[str, Any]) -> str:
    strategy = metrics.get("strategy")
    if strategy is None:
        return _("N/A (no hole was visited)")
    if metrics.get("strategy_source") == "manual":
        return _("{strategy} (manually corrected; automatic result: {auto})").format(
            strategy=strategy_label(strategy), auto=strategy_label(metrics.get("strategy_auto"))
        )
    return _("{strategy} (automatic)").format(strategy=strategy_label(strategy))


def _unavailable_text(metrics: Mapping[str, Any]) -> str:
    """Why the Barnes metrics are missing, in words (never the raw token alone)."""
    reasons: dict[str, Callable[[], str]] = {
        "no_rois": lambda: _("The video has no ROIs; the Barnes metrics need the hole ROIs."),
        "layout_unresolved": lambda: _(
            "The hole layout could not be read from the ROI names: the escape hole or "
            "some decoy holes are missing."
        ),
        "multi_animal": lambda: _(
            "More than one animal was tracked; the Barnes metrics need a single animal."
        ),
        "multi_aquarium": lambda: _(
            "Multi-aquarium videos are analysed one arena at a time; the Barnes metrics "
            "were not computed."
        ),
        "no_trajectory": lambda: _("There is no trajectory inside the trial to measure."),
        "unknown_protocol": lambda: _("The configured protocol is not known to this version."),
        "unregistered": lambda: _("The Barnes protocol is not available in this version."),
        "exception": lambda: _("The Barnes metrics failed with an error."),
    }
    reason = str(metrics.get("reason") or "")
    text = reasons[reason]() if reason in reasons else _("The Barnes metrics are unavailable.")
    error = metrics.get("error")
    return f"{text} ({error})" if error else text


def _add_table(document: DocxDocument, rows: list[tuple[str, str]]) -> None:
    table = document.add_table(rows=1, cols=2)
    table.style = "Table Grid"
    table.cell(0, 0).text = _("Metric")
    table.cell(0, 1).text = _("Value")
    for label, value in rows:
        cells = table.add_row().cells
        cells[0].text = label
        cells[1].text = value


def _metric_rows(metrics: Mapping[str, Any]) -> list[tuple[str, str]]:
    probe = metrics.get("trial_type") == "probe"
    features = metrics.get("strategy_features") or {}
    rows: list[tuple[str, str]] = [
        (_("Trial type"), _trial_label(metrics.get("trial_type"))),
        (
            _("Encounter latency (first nose poke in the escape hole)"),
            _latency(metrics.get("encounter_latency_s"), metrics.get("encounter_censored")),
        ),
    ]
    if not probe:
        rows.append((_("Entry latency (four paws in)"), _entry_text(metrics)))
    rows.extend(
        [
            (
                _("Primary errors (before the first encounter)"),
                _count(metrics.get("primary_errors")),
            ),
            (_("Total errors"), _count(metrics.get("total_errors"))),
            (_("Perseverative errors"), _count(metrics.get("perseverative_errors"))),
            (_("Path to the encounter"), _centimetres(metrics.get("primary_path_length_cm"))),
        ]
    )
    if not probe:
        rows.append((_("Path to the entry"), _centimetres(metrics.get("entry_path_length_cm"))))
    quadrant_s = metrics.get("target_quadrant_time_s")
    quadrant_pct = metrics.get("target_quadrant_time_pct")
    rows.append(
        (
            _("Time in the target quadrant"),
            _NOT_AVAILABLE
            if quadrant_s is None
            else f"{float(quadrant_s):.2f} s ({float(quadrant_pct or 0.0):.1f} %)",
        )
    )
    rows.append((_("Search strategy"), _strategy_text(metrics)))
    fraction = features.get("adjacent_transition_fraction")
    rows.append(
        (
            _("Strategy features"),
            _(
                "errors before the target: {errors}; centre crossings: {crossings}; "
                "adjacent transitions: {fraction}"
            ).format(
                errors=features.get("errors_before_target", _NOT_AVAILABLE),
                crossings=features.get("center_crossings", _NOT_AVAILABLE),
                fraction=_NOT_AVAILABLE if fraction is None else f"{float(fraction):.2f}",
            ),
        )
    )
    if probe:
        offset = metrics.get("probe_first_hole_offset")
        rows.extend(
            [
                (
                    _("First hole visited (offset from the target)"),
                    _NOT_AVAILABLE if offset is None else f"{int(offset):+d}",
                ),
                (_("First hole score"), _count(metrics.get("probe_first_hole_score"))),
                (
                    _("Latency to the first error"),
                    _seconds(metrics.get("probe_first_error_latency_s")),
                ),
                (_("Attempts until the target"), _count(metrics.get("probe_attempts_to_target"))),
            ]
        )
    return rows


def _visits_by_distance_text(metrics: Mapping[str, Any]) -> str:
    """``distance: visits`` pairs; keys are ints in memory and str after JSON."""
    histogram = metrics.get("visits_by_distance") or {}
    pairs = sorted((int(distance), int(count)) for distance, count in histogram.items())
    return "; ".join(f"{distance}: {count}" for distance, count in pairs)


def append_barnes_section(
    document: DocxDocument, ctx: ReporterContext, metrics: Mapping[str, Any]
) -> None:
    """Append the Barnes results: table, caveats and the two Barnes figures.

    A status other than ``ok`` still gets its heading, with the reason in words, so
    a missing result is never mistaken for "nothing to report".
    """
    document.add_heading(_("Barnes Maze Results"), level=2)
    status = metrics.get("status")
    if status != "ok":
        document.add_paragraph(_("Status: {status}").format(status=status or _("N/A")))
        document.add_paragraph(_unavailable_text(metrics))
        document.add_paragraph(_("See the validation appendix for the details."))
        return

    _add_table(document, _metric_rows(metrics))
    if metrics.get("encounter_censored") or metrics.get("entry_censored"):
        document.add_paragraph(
            _(
                "A censored latency (≥) means the event did not happen before the end of the "
                "trial: the value is the trial ceiling, a lower bound, not a measurement."
            )
        )
    distances = _visits_by_distance_text(metrics)
    if distances:
        document.add_paragraph(
            _("Visits by hole distance (distance: visits): {pairs}").format(pairs=distances)
        )
    _append_figures(document, ctx, metrics)


def _append_figures(
    document: DocxDocument, ctx: ReporterContext, metrics: Mapping[str, Any]
) -> None:
    from zebtrack.analysis.protocols.barnes.contract import parse_barnes_params
    from zebtrack.core.services.experiment_profile import resolve_experiment_profile

    profile = resolve_experiment_profile(behavioral_config=ctx.behavioral_config)
    params, _warnings = parse_barnes_params(profile.protocol_params)
    visits = list(metrics.get("visit_sequence") or [])
    generator = ctx.viz_generator
    configs: list[tuple[Callable[[Any], Any], str]] = [
        (
            lambda ax: generator.generate_barnes_hole_diagram(
                ax, metrics, quadrant_half_holes=params.quadrant_half_holes
            ),
            _("Hole visits"),
        ),
        (
            lambda ax: generator.generate_barnes_trajectory_plot(ax, ctx.video_path, visits),
            _("Trajectory and hole visits"),
        ),
    ]
    for memfile, name in generator.generate_plots_parallel(configs):
        if isinstance(memfile, io.BytesIO) and memfile.getbuffer().nbytes > 0:
            document.add_paragraph(_("Figure: {name}").format(name=name))
            document.add_picture(memfile, width=Inches(5.5))
