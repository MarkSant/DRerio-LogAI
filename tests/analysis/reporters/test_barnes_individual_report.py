"""Individual Barnes report end to end: ``.docx`` section, ``barnes_visits`` sheet, figures.

A scripted 18-hole rat goes through the REAL analysis (``ReporterContext`` ->
``AnalysisService.run_full_analysis``) and the real Word and Excel reporters; the
assertions read the produced files, not the reporter's internals.
"""

from __future__ import annotations

import io
import math
from pathlib import Path

import pandas as pd
import pytest
from docx import Document
from matplotlib.patches import Wedge
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
    return [
        p.text
        for p in Document(str(path)).paragraphs
        if p.style is not None and p.style.name.startswith("Heading")
    ]


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
        patch = target.get_bbox_patch()
        assert patch is not None
        assert patch.get_facecolor()[:3] == pytest.approx((1.0, 0.843, 0.0), abs=0.01)
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


def _diagram_text_positions(metrics) -> dict[str, tuple[float, float]]:
    """Where each visit-order label sits on the ring diagram (axes coordinates)."""
    from matplotlib import pyplot as plt

    context = barnes_context(scripted_rat(0))
    fig = context.viz_generator.generate_barnes_hole_diagram(None, metrics, quadrant_half_holes=2)
    try:
        # the visit orders sit OUTSIDE the ring (radius 1); the counts sit on it
        return {
            t.get_text(): t.get_position()
            for t in fig.axes[0].texts
            if math.hypot(*t.get_position()) > 1.05
        }
    finally:
        plt.close(fig)


def _visit(order: int, offset: int) -> dict:
    return {"order": order, "offset": offset, "roi": f"h{offset}", "is_target": offset == 0}


def test_the_ring_puts_the_target_on_top_and_clockwise_offsets_on_the_right():
    metrics = {
        "n_holes": 18,
        "visit_sequence": [_visit(1, 0), _visit(2, 3), _visit(3, -3), _visit(4, 9)],
    }

    at = _diagram_text_positions(metrics)

    target, clockwise, counter, opposite = at["1"], at["2"], at["3"], at["4"]
    assert target[0] == pytest.approx(0.0, abs=1e-9)
    assert target[1] > 0  # the target is at the top
    assert clockwise[0] > 0 > counter[0]  # +3 is on the right (clockwise), -3 on the left
    assert clockwise[0] == pytest.approx(-counter[0])
    assert opposite[0] == pytest.approx(0.0, abs=1e-9)
    assert opposite[1] < 0  # the opposite hole is at the bottom


def test_the_shaded_quadrant_spans_the_target_and_two_holes_each_side():
    from matplotlib import pyplot as plt

    context = barnes_context(scripted_rat(0))
    metrics = {"n_holes": 18, "visit_sequence": [_visit(1, 0)]}

    fig = context.viz_generator.generate_barnes_hole_diagram(None, metrics, quadrant_half_holes=2)

    try:
        [wedge] = [p for p in fig.axes[0].patches if isinstance(p, Wedge)]
        assert wedge.theta2 - wedge.theta1 == pytest.approx(5 * 360 / 18)  # 5 holes
        assert (wedge.theta1 + wedge.theta2) / 2 == pytest.approx(90.0)  # centred on the top
    finally:
        plt.close(fig)


def test_the_target_marker_on_the_trajectory_is_gold_and_decoys_are_white():
    from matplotlib import pyplot as plt

    context = barnes_context(scripted_rat(2, 0))
    visits = context.report["protocol_metrics"]["visit_sequence"]

    fig = context.viz_generator.generate_barnes_trajectory_plot(None, None, visits)

    try:
        boxes = {t.get_text(): t.get_bbox_patch() for t in fig.axes[0].texts}
        decoy, target = boxes["1"], boxes["2"]
        assert decoy is not None
        assert target is not None
        assert decoy.get_facecolor()[:3] == pytest.approx((1.0, 1.0, 1.0))
        assert target.get_facecolor()[:3] != pytest.approx((1.0, 1.0, 1.0))
    finally:
        plt.close(fig)


def test_a_failed_trial_never_leaks_a_visit_sequence_into_the_sheet(tmp_path):
    context = barnes_context(scripted_rat(3, 2, 0))
    visits = context.report["protocol_metrics"]["visit_sequence"]
    assert visits  # there is something to leak
    context.report["protocol_metrics"] = {
        "status": "error",
        "protocol": "barnes",
        "version": 1,
        "reason": "exception",
        "visit_sequence": visits,
    }
    out = tmp_path / "summary.xlsx"

    ExcelReporter(context).export_summary(out)

    assert pd.read_excel(out, sheet_name=EXCEL_VISITS_SHEET).empty


def test_a_missing_value_is_na_and_never_zero_in_the_word_table(tmp_path):
    context = barnes_context(
        scripted_rat(3, 2, 0), protocol_inputs={"barnes": {"trial_type": "probe"}}
    )
    context.report["protocol_metrics"].update(
        encounter_latency_s=None,
        encounter_censored=None,
        primary_errors=None,
        total_errors=None,
        perseverative_errors=None,
        probe_first_hole_score=None,
        probe_attempts_to_target=None,
        probe_first_error_latency_s=None,
        probe_first_hole_offset=None,
    )

    rows = _barnes_rows(_word(context, tmp_path))

    for label in (
        "Encounter latency (first nose poke in the escape hole)",
        "Primary errors (before the first encounter)",
        "Total errors",
        "Perseverative errors",
        "First hole visited (offset from the target)",
        "First hole score",
        "Latency to the first error",
        "Attempts until the target",
    ):
        assert rows[label] == "N/A", label


def test_the_visits_sheet_is_written_when_there_is_no_per_animal_sheet(tmp_path):
    context = barnes_context(scripted_rat(3, 2, 0))
    context.per_animal_data = pd.DataFrame()  # nothing to write for por_animal
    out = tmp_path / "summary.xlsx"

    ExcelReporter(context).export_summary(out)

    sheets = pd.read_excel(out, sheet_name=None)
    assert set(sheets) == {"Sheet1", EXCEL_VISITS_SHEET}
    assert len(sheets[EXCEL_VISITS_SHEET]) == 3


def test_a_visited_hole_is_filled_darker_the_more_it_was_visited():
    from matplotlib import pyplot as plt
    from matplotlib.patches import Circle

    context = barnes_context(scripted_rat(0))
    metrics = {
        "n_holes": 18,
        "visit_sequence": [_visit(1, 3), _visit(2, 3), _visit(3, 3), _visit(4, 2)],
    }

    fig = context.viz_generator.generate_barnes_hole_diagram(None, metrics, quadrant_half_holes=2)

    try:
        holes = [p for p in fig.axes[0].patches if isinstance(p, Circle)]
        by_offset: dict[int, tuple[float, float, float]] = {}
        for hole in holes[1:]:  # the first circle is the outer ring
            x, y = hole.center
            angle = math.atan2(x, y)  # clockwise from the top
            by_offset[round(angle * 18 / (2 * math.pi))] = tuple(hole.get_facecolor()[:3])  # type: ignore[assignment]
        never, once, thrice = by_offset[5], by_offset[2], by_offset[3]
        assert never == pytest.approx((0.88, 0.88, 0.88))
        assert once != pytest.approx(never)
        assert sum(thrice) < sum(once) < sum(never)  # darker with more visits
    finally:
        plt.close(fig)
