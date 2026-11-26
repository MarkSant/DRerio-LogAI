"""Individual Barnes report end to end: ``.docx`` section, ``barnes_visits`` sheet, figures.

A scripted 18-hole rat goes through the REAL analysis (``ReporterContext`` ->
``AnalysisService.run_full_analysis``) and the real Word and Excel reporters; the
assertions read the produced files, not the reporter's internals.
"""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import pytest
from docx import Document
from tests.analysis.reporters.barnes_report_builders import (
    BARNES_CONFIG,
    barnes_context,
    scripted_rat,
)

from zebtrack.analysis.protocols.barnes.contract import (
    EXCEL_VISIT_COLUMNS,
    EXCEL_VISITS_SHEET,
    VISIT_FIELDS,
)
from zebtrack.analysis.reporters import ExcelReporter, WordReporter
from zebtrack.analysis.reporters.barnes_section import strategy_label

pytestmark = pytest.mark.unit


def _docx_text(path: Path) -> str:
    document = Document(str(path))
    parts = [p.text for p in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            parts.extend(cell.text for cell in row.cells)
    return "\n".join(parts)


def _headings(path: Path) -> list[str]:
    return [p.text for p in Document(str(path)).paragraphs if p.style.name.startswith("Heading")]


def _word(context, tmp_path: Path) -> Path:
    out = tmp_path / "report.docx"
    WordReporter(context).export_individual_report(out)
    return out


def _barnes_rows(path: Path) -> dict[str, str]:
    """The label -> value rows of the Barnes table (the one that has a strategy row)."""
    for table in Document(str(path)).tables:
        rows = {row.cells[0].text: row.cells[1].text for row in table.rows}
        if "Search strategy" in rows:
            return rows
    raise AssertionError("no Barnes table in the report")


# --- the Word section ------------------------------------------------------------


def test_the_word_report_has_a_barnes_section_after_the_metrics_summary(tmp_path):
    out = _word(barnes_context(scripted_rat(3, 2, 0)), tmp_path)

    headings = _headings(out)

    assert "Barnes Maze Results" in headings
    assert headings.index("Barnes Maze Results") == headings.index("Metrics Summary") + 1


def test_the_barnes_table_states_latencies_errors_and_the_automatic_strategy(tmp_path):
    context = barnes_context(scripted_rat(3, 2, 0))
    metrics = context.report["protocol_metrics"]
    out = _word(context, tmp_path)

    barnes_rows = _barnes_rows(out)

    assert barnes_rows["Trial type"] == "Training"
    assert barnes_rows["Primary errors (before the first encounter)"] == "2"
    assert barnes_rows["Total errors"] == str(metrics["total_errors"])
    assert barnes_rows["Encounter latency (first nose poke in the escape hole)"] == (
        f"{metrics['encounter_latency_s']:.2f} s"
    )
    assert barnes_rows["Search strategy"] == (f"{strategy_label(metrics['strategy'])} (automatic)")
    assert "Visits by hole distance" in _docx_text(out)


def test_a_manual_correction_is_marked_with_the_automatic_result(tmp_path):
    context = barnes_context(
        scripted_rat(3, 2, 0), protocol_inputs={"barnes": {"strategy_override": "random"}}
    )
    auto = context.report["protocol_metrics"]["strategy_auto"]

    text = _docx_text(_word(context, tmp_path))

    assert f"Random (manually corrected; automatic result: {strategy_label(auto)})" in text


def test_a_censored_latency_is_a_lower_bound_and_never_zero(tmp_path):
    # the rat never reaches the escape hole: the encounter is censored at the ceiling
    context = barnes_context(scripted_rat(3, 2, -2))

    out = _word(context, tmp_path)

    metrics = context.report["protocol_metrics"]
    assert metrics["encounter_censored"] is True
    text = _docx_text(out)
    assert f"≥ {metrics['encounter_latency_s']:.2f} s (censored)" in text
    assert "lower bound" in text


def test_a_probe_trial_shows_probe_metrics_and_no_entry_row(tmp_path):
    context = barnes_context(
        scripted_rat(2, 0), protocol_inputs={"barnes": {"trial_type": "probe"}}
    )

    out = _word(context, tmp_path)

    rows = _barnes_rows(out)
    assert rows["Trial type"] == "Probe"
    assert rows["First hole visited (offset from the target)"] == "+2"
    assert rows["First hole score"] == "3"
    assert rows["Attempts until the target"] == "2"
    assert "Entry latency (four paws in)" not in rows


def test_an_unavailable_result_gets_its_heading_and_the_reason_in_words(tmp_path):
    context = barnes_context(scripted_rat(0))
    context.report["protocol_metrics"] = {
        "status": "unavailable",
        "protocol": "barnes",
        "version": 1,
        "reason": "no_rois",
    }

    out = _word(context, tmp_path)

    text = _docx_text(out)
    assert "Barnes Maze Results" in _headings(out)
    assert "Status: unavailable" in text
    assert "The video has no ROIs; the Barnes metrics need the hole ROIs." in text
    assert "Search strategy" not in text


def test_the_barnes_figures_are_added_and_the_generic_fish_figures_are_suppressed(tmp_path):
    out = _word(barnes_context(scripted_rat(3, 2, 0)), tmp_path)

    text = _docx_text(out)

    assert "Figure: Hole visits" in text
    assert "Figure: Trajectory and hole visits" in text
    assert "Thigmotaxis" not in text
    assert "Geotaxis" not in text
    # the generic figures that stay
    assert "Figure: Trajectory" in text
    assert "Figure: Heatmap" in text


def test_the_barnes_columns_do_not_repeat_in_the_generic_summary_table(tmp_path):
    out = _word(barnes_context(scripted_rat(3, 2, 0)), tmp_path)

    summary = next(
        t for t in Document(str(out)).tables if t.cell(0, 0).text == "Metric" and len(t.rows) > 10
    )
    labels = [row.cells[0].text for row in summary.rows]

    assert not [label for label in labels if label.startswith("Barnes ")]


def test_a_generic_report_has_no_barnes_content(tmp_path):
    generic = barnes_context(scripted_rat(0), behavioral_config={"aquarium_perspective": "lateral"})

    out = _word(generic, tmp_path)

    text = _docx_text(out)
    assert "Barnes" not in text
    assert "Figure: Thigmotaxis (Wall Distance)" in text
    assert "Figure: Hole visits" not in text


# --- the Excel sheet --------------------------------------------------------------


def test_the_excel_summary_has_a_barnes_visits_sheet_with_the_visit_sequence(tmp_path):
    context = barnes_context(scripted_rat(3, 2, 0))
    out = tmp_path / "summary.xlsx"

    ExcelReporter(context).export_summary(out)

    sheets = pd.read_excel(out, sheet_name=None)
    assert EXCEL_VISITS_SHEET == "barnes_visits"
    visits = sheets[EXCEL_VISITS_SHEET]
    sequence = context.report["protocol_metrics"]["visit_sequence"]
    assert list(visits.columns) == list(EXCEL_VISIT_COLUMNS)
    assert list(visits["experiment_id"]) == ["RAT_01"] * len(sequence)
    assert (
        list(visits["roi"]) == [v["roi"] for v in sequence] == ["buraco_+03", "buraco_+02", "toca"]
    )
    assert list(visits["order"]) == [1, 2, 3]
    assert list(visits["is_target"]) == [False, False, True]
    for field in VISIT_FIELDS:
        assert field in visits.columns
    assert next(iter(sheets)) == "Sheet1"


def test_the_main_sheet_carries_the_barnes_columns_with_display_names(tmp_path):
    out = tmp_path / "summary.xlsx"

    ExcelReporter(barnes_context(scripted_rat(3, 2, 0))).export_summary(out)

    main = pd.read_excel(out, sheet_name="Sheet1")
    columns = list(main.columns)
    assert "Barnes Primary Errors" in columns
    assert "Barnes Visits at Distance 3" in columns
    assert columns.index("Barnes Status") > columns.index("Analysis Window End Reason")
    assert main["Barnes Primary Errors"].iloc[0] == 2


def test_the_visits_sheet_is_written_even_when_empty(tmp_path):
    context = barnes_context(scripted_rat(0))
    context.report["protocol_metrics"] = {
        "status": "unavailable",
        "protocol": "barnes",
        "version": 1,
        "reason": "layout_unresolved",
    }
    out = tmp_path / "summary.xlsx"

    ExcelReporter(context).export_summary(out)

    visits = pd.read_excel(out, sheet_name=EXCEL_VISITS_SHEET)
    assert visits.empty
    assert list(visits.columns) == list(EXCEL_VISIT_COLUMNS)


def test_a_generic_workbook_has_no_barnes_sheet_and_no_barnes_column(tmp_path):
    generic = barnes_context(scripted_rat(0), behavioral_config={"aquarium_perspective": "lateral"})
    out = tmp_path / "summary.xlsx"

    ExcelReporter(generic).export_summary(out)

    sheets = pd.read_excel(out, sheet_name=None)
    assert EXCEL_VISITS_SHEET not in sheets
    assert not [c for c in sheets["Sheet1"].columns if str(c).startswith("Barnes")]


def test_csv_export_keeps_working_for_a_barnes_project(tmp_path):
    out = tmp_path / "summary.csv"

    ExcelReporter(barnes_context(scripted_rat(3, 2, 0))).export_summary(out)

    frame = pd.read_csv(out)
    assert "Barnes Strategy" in frame.columns


# --- the figures ------------------------------------------------------------------


def test_the_hole_diagram_counts_visits_and_marks_the_target():
    from matplotlib import pyplot as plt

    context = barnes_context(scripted_rat(3, 2, 3, 0))
    metrics = context.report["protocol_metrics"]

    fig = context.viz_generator.generate_barnes_hole_diagram(None, metrics, quadrant_half_holes=2)

    try:
        ax = fig.axes[0]
        shown = sorted(t.get_text() for t in ax.texts)
        # the +3 hole was visited twice (orders 1 and 3); +2 and the target once each
        counts = ["2", "1", "1"]  # +3, +2, target (inside the holes)
        orders = ["1,3", "2", "4"]  # outside the ring
        assert [t for t in shown if t != "target at top"] == sorted(counts + orders)
        # 18 holes + the quadrant wedge + the outer circle
        circles = [p for p in ax.patches if p.__class__.__name__ == "Circle"]
        assert len(circles) == 18 + 1
        assert len([p for p in ax.patches if p.__class__.__name__ == "Wedge"]) == 1
        edges = sorted({round(p.get_linewidth(), 1) for p in circles})
        assert 2.6 in edges  # the target's heavier outline
    finally:
        plt.close(fig)


def test_the_hole_diagram_without_a_layout_says_so():
    from matplotlib import pyplot as plt

    context = barnes_context(scripted_rat(0))

    fig = context.viz_generator.generate_barnes_hole_diagram(None, {}, quadrant_half_holes=2)

    try:
        assert [t.get_text() for t in fig.axes[0].texts] == ["No hole layout"]
    finally:
        plt.close(fig)


def test_the_numbered_trajectory_labels_each_visited_hole_with_its_orders():
    from matplotlib import pyplot as plt

    context = barnes_context(scripted_rat(3, 2, 3, 0))
    visits = context.report["protocol_metrics"]["visit_sequence"]

    fig = context.viz_generator.generate_barnes_trajectory_plot(None, None, visits)

    try:
        labels = sorted(t.get_text() for t in fig.axes[0].texts)
        assert labels == ["1,3", "2", "4"]
        target = next(t for t in fig.axes[0].texts if t.get_text() == "4")
        assert target.get_bbox_patch().get_facecolor()[:3] == pytest.approx(
            (1.0, 0.843, 0.0), abs=0.01
        )
    finally:
        plt.close(fig)


def test_a_visit_to_an_unknown_roi_is_left_unmarked():
    from matplotlib import pyplot as plt

    context = barnes_context(scripted_rat(0))

    fig = context.viz_generator.generate_barnes_trajectory_plot(
        None, None, [{"order": 1, "roi": "no_such_roi", "is_target": False}]
    )

    try:
        assert len(fig.axes[0].texts) == 0
    finally:
        plt.close(fig)


def test_the_word_figures_are_real_pngs(tmp_path):
    out = _word(barnes_context(scripted_rat(3, 2, 0)), tmp_path)

    images = [
        rel.target_part.blob
        for rel in Document(str(out)).part.rels.values()
        if "image" in rel.reltype
    ]

    assert images
    assert all(blob.startswith(b"\x89PNG") for blob in images)
    assert BARNES_CONFIG["protocol"] == "barnes"
    assert io.BytesIO(images[0]).getbuffer().nbytes > 1000
