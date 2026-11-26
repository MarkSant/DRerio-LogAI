"""Barnes aggregates (learning curves, strategy distribution, probe): numbers and censoring."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from docx import Document
from matplotlib.patches import Rectangle
from tests.analysis.reporters.barnes_report_builders import tidy_row

from zebtrack.analysis.data_transformer import DataTransformer
from zebtrack.analysis.reporters.barnes_aggregates import (
    barnes_sheets,
    is_barnes_frame,
    learning_curve_figure,
    learning_curves,
    probe_comparison,
    probe_figure,
    render_barnes_aggregates,
    render_barnes_per_animal,
    strategy_distribution,
    strategy_figure,
    to_internal_columns,
)

pytestmark = pytest.mark.unit


def _frame(*rows: dict) -> pd.DataFrame:
    return pd.DataFrame(list(rows))


def _probe_row(subject: str, **fields) -> dict:
    return tidy_row("CTL", "Dia_6", subject, trial_type="probe", **fields)


def _curve(curves: pd.DataFrame, group: str, day: str, metric: str) -> pd.Series:
    match = curves[
        (curves["group"] == group) & (curves["day"] == day) & (curves["metric"] == metric)
    ]
    assert len(match) == 1
    return match.iloc[0]


def _text(document) -> str:
    parts = [p.text for p in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            parts.extend(cell.text for cell in row.cells)
    return "\n".join(parts)


# --- learning curves ----------------------------------------------------------------


def test_the_learning_curve_is_mean_and_sem_per_group_and_day():
    df = _frame(
        tidy_row("CTL", "Dia_1", "1", encounter=20.0, primary=2, total=4),
        tidy_row("CTL", "Dia_1", "2", encounter=40.0, primary=4, total=6),
        tidy_row("CTL", "Dia_2", "1", encounter=10.0, primary=0, total=1),
    )

    curves = learning_curves(df)

    point = _curve(curves, "CTL", "Dia_1", "encounter_latency_s")
    assert point["n"] == 2
    assert point["mean"] == pytest.approx(30.0)
    assert point["sem"] == pytest.approx(10.0)  # std 14.142 / sqrt(2)
    assert _curve(curves, "CTL", "Dia_1", "primary_errors")["mean"] == pytest.approx(3.0)
    assert _curve(curves, "CTL", "Dia_1", "total_errors")["mean"] == pytest.approx(5.0)
    assert _curve(curves, "CTL", "Dia_2", "encounter_latency_s")["mean"] == pytest.approx(10.0)


def test_a_single_trial_has_a_mean_and_no_sem_never_zero():
    curves = learning_curves(_frame(tidy_row("CTL", "Dia_1", "1", encounter=20.0)))

    point = _curve(curves, "CTL", "Dia_1", "encounter_latency_s")

    assert point["n"] == 1
    assert point["mean"] == pytest.approx(20.0)
    assert math.isnan(point["sem"])


def test_censored_latencies_are_counted_flagged_and_kept_out_of_the_observed_mean():
    df = _frame(
        tidy_row("CTL", "Dia_1", "1", encounter=20.0),
        tidy_row("CTL", "Dia_1", "2", encounter=240.0, encounter_censored=True),
        tidy_row("CTL", "Dia_1", "3", encounter=40.0),
    )

    point = _curve(learning_curves(df), "CTL", "Dia_1", "encounter_latency_s")

    assert point["n"] == 3
    assert point["n_censored"] == 1
    assert point["mean"] == pytest.approx((20 + 240 + 40) / 3)  # at the ceiling: a lower bound
    assert point["mean_observed"] == pytest.approx(30.0)  # uncensored trials only


def test_a_missing_entry_latency_is_not_a_trial_and_not_a_zero():
    df = _frame(
        tidy_row("CTL", "Dia_1", "1", entry=None, entry_censored=None),
        tidy_row("CTL", "Dia_1", "2", entry=50.0),
    )

    point = _curve(learning_curves(df), "CTL", "Dia_1", "entry_latency_s")

    assert point["n"] == 1
    assert point["mean"] == pytest.approx(50.0)


def test_a_block_with_no_entry_at_all_has_an_empty_mean():
    df = _frame(tidy_row("CTL", "Dia_1", "1", entry=None, entry_censored=None))

    point = _curve(learning_curves(df), "CTL", "Dia_1", "entry_latency_s")

    assert point["n"] == 0
    assert math.isnan(point["mean"])


def test_probe_trials_and_failed_trials_stay_out_of_the_training_curves():
    df = _frame(
        tidy_row("CTL", "Dia_1", "1", encounter=20.0),
        tidy_row("CTL", "Dia_1", "2", trial_type="probe", encounter=999.0),
        tidy_row("CTL", "Dia_1", "3", status="unavailable"),
    )

    point = _curve(learning_curves(df), "CTL", "Dia_1", "encounter_latency_s")

    assert point["n"] == 1
    assert point["mean"] == pytest.approx(20.0)


def test_days_sort_naturally_and_groups_keep_their_order():
    df = _frame(
        tidy_row("B", "Dia_10", "1"),
        tidy_row("B", "Dia_2", "1"),
        tidy_row("A", "Dia_1", "1"),
    )

    curves = learning_curves(df)

    blocks = list(dict.fromkeys(zip(curves["group"], curves["day"], strict=True)))
    assert blocks == [("B", "Dia_2"), ("B", "Dia_10"), ("A", "Dia_1")]


# --- strategy ---------------------------------------------------------------------


def test_the_strategy_distribution_is_a_fraction_of_trials_with_a_strategy():
    df = _frame(
        tidy_row("CTL", "Dia_1", "1", strategy="direct"),
        tidy_row("CTL", "Dia_1", "2", strategy="serial"),
        tidy_row("CTL", "Dia_1", "3", strategy="serial"),
        tidy_row("CTL", "Dia_1", "4", strategy=None),  # no hole visited: not in the denominator
    )

    dist = strategy_distribution(df)

    by = dict(zip(dist["strategy"], dist["fraction"], strict=True))
    assert by == {"direct": pytest.approx(1 / 3), "serial": pytest.approx(2 / 3), "random": 0.0}
    assert set(dist["n_trials"]) == {3}


def test_a_manually_corrected_strategy_counts_as_its_corrected_value():
    df = _frame(tidy_row("CTL", "Dia_1", "1", strategy="random", strategy_source="manual"))

    dist = strategy_distribution(df)

    assert dist.set_index("strategy").loc["random", "n"] == 1


# --- probe ------------------------------------------------------------------------


def test_the_probe_comparison_is_per_group_and_skips_values_that_do_not_exist():
    df = _frame(
        _probe_row(
            "1",
            probe_offset=-3,
            probe_score=4,
            probe_error_latency=12.0,
            probe_attempts=2,
            quadrant_pct=30.0,
        ),
        _probe_row(
            "2",
            probe_offset=0,
            probe_score=1,
            probe_error_latency=None,
            probe_attempts=1,
            quadrant_pct=50.0,
        ),
        tidy_row("CTL", "Dia_1", "3", encounter=10.0),  # training: not a probe
    )

    probe = probe_comparison(df).set_index("metric")

    assert probe.loc["first_hole_score", "mean"] == pytest.approx(2.5)
    assert probe.loc["first_hole_distance", "mean"] == pytest.approx(1.5)  # |-3| and |0|
    assert probe.loc["first_error_latency_s", "n"] == 1  # the direct hit has no error latency
    assert probe.loc["first_error_latency_s", "mean"] == pytest.approx(12.0)
    assert probe.loc["target_quadrant_pct", "mean"] == pytest.approx(40.0)


def test_without_probe_trials_the_probe_comparison_is_empty():
    assert probe_comparison(_frame(tidy_row("CTL", "Dia_1", "1"))).empty


# --- columns and detection -----------------------------------------------------------


def test_display_names_map_back_to_the_internal_columns():
    internal = _frame(tidy_row("CTL", "Dia_1", "1", primary=2))
    shown = DataTransformer().prepare_for_display(internal)

    back = to_internal_columns(shown)

    for column in ("barnes_status", "barnes_primary_errors", "barnes_visits_d03"):
        assert column in back.columns
    assert back["barnes_primary_errors"].iloc[0] == 2
    assert to_internal_columns(internal).equals(internal)


def test_only_a_frame_with_barnes_columns_is_a_barnes_frame():
    assert is_barnes_frame(_frame(tidy_row("CTL", "Dia_1", "1")))
    assert is_barnes_frame(DataTransformer().prepare_for_display(_frame(tidy_row("A", "d", "1"))))
    assert not is_barnes_frame(pd.DataFrame({"group_id": ["A"], "total_distance_cm": [1.0]}))


def test_the_workbook_sheets_have_stable_english_names_and_leave_empty_ones_out():
    df = _frame(tidy_row("CTL", "Dia_1", "1"))

    assert list(barnes_sheets(df)) == ["barnes_learning_curves", "barnes_strategy"]
    probe_df = _frame(_probe_row("1", probe_offset=1, probe_score=2, probe_attempts=3))
    assert "barnes_probe" in barnes_sheets(probe_df)
    assert barnes_sheets(pd.DataFrame({"group_id": ["A"]})) == {}


# --- Word ---------------------------------------------------------------------------


def test_the_word_section_shows_censoring_next_to_the_latency():
    df = _frame(
        tidy_row("CTL", "Dia_1", "1", encounter=20.0),
        tidy_row("CTL", "Dia_1", "2", encounter=240.0, encounter_censored=True),
    )
    document = Document()

    written = render_barnes_aggregates(document, df)

    text = _text(document)
    assert written is True
    assert "Barnes Maze Results" in text
    assert "130.00 ± 110.00 [1/2 censored]" in text
    assert "lower bound" in text


def test_a_generic_frame_writes_nothing():
    document = Document()

    written = render_barnes_aggregates(document, pd.DataFrame({"group_id": ["A"]}))

    assert written is False
    assert len(document.paragraphs) == 0
    assert not document.tables


def test_a_barnes_frame_without_a_computed_trial_says_so():
    document = Document()

    render_barnes_aggregates(document, _frame(tidy_row("CTL", "Dia_1", "1", status="unavailable")))

    assert "No Barnes trial with computed metrics" in _text(document)


def test_the_learning_curve_figure_is_only_added_for_more_than_one_day():
    one_day = _frame(tidy_row("CTL", "Dia_1", "1"), tidy_row("CTL", "Dia_1", "2"))
    two_days = _frame(tidy_row("CTL", "Dia_1", "1"), tidy_row("CTL", "Dia_2", "1"))
    single, multi = Document(), Document()

    render_barnes_aggregates(single, one_day)
    render_barnes_aggregates(multi, two_days)

    assert len(single.inline_shapes) == 1  # strategy bars only
    assert len(multi.inline_shapes) == 2  # + the learning curves


def test_the_strategy_probe_and_curve_figures_draw_something():
    df = _frame(
        tidy_row("CTL", "Dia_1", "1", encounter=240.0, encounter_censored=True),
        tidy_row("CTL", "Dia_2", "1"),
        _probe_row("2", probe_offset=2, probe_score=3, probe_attempts=2),
    )

    curve = learning_curve_figure(learning_curves(df))
    strategy = strategy_figure(strategy_distribution(df))
    probe = probe_figure(probe_comparison(df))

    assert curve is not None
    assert len(curve.axes) == 4
    # the censored point is drawn hollow and labelled "1/1"
    assert "1/1" in [t.get_text() for ax in curve.axes for t in ax.texts]
    assert strategy is not None
    assert len(strategy.axes[0].patches) == 6  # 3 strategies x 2 blocks
    assert probe is not None
    assert len(probe.axes) == 2
    assert learning_curve_figure(pd.DataFrame()) is None
    assert strategy_figure(pd.DataFrame()) is None
    assert probe_figure(pd.DataFrame()) is None


def test_the_per_animal_table_marks_censoring_corrections_and_failures():
    corrected = tidy_row(
        "CTL",
        "Dia_1",
        "2",
        encounter=240.0,
        encounter_censored=True,
        strategy="random",
        strategy_source="manual",
    )
    frame = _frame(
        {**tidy_row("CTL", "Dia_1", "1", encounter=20.0), "animal": "R1"},
        {**corrected, "animal": "R2"},
        {**tidy_row("CTL", "Dia_1", "3", status="unavailable"), "animal": "R3"},
    )
    document = Document()

    written = render_barnes_per_animal(document, frame)

    rows = {r.cells[0].text: [c.text for c in r.cells] for r in document.tables[0].rows[1:]}
    assert written is True
    assert rows["R1"][2] == "20.00"
    assert rows["R2"][2] == "≥ 240.00 s (censored)"
    assert rows["R2"][6] == "Random (corrected)"
    assert rows["R3"][1] == "Status: unavailable"
    assert rows["R3"][2:] == ["N/A"] * 5


def test_the_per_animal_table_reads_the_partial_reports_display_columns():
    internal = _frame({**tidy_row("CTL", "Dia_1", "1", primary=3), "animal": "R1"})
    shown = DataTransformer().prepare_for_display(internal)
    document = Document()

    render_barnes_per_animal(document, shown)

    assert [c.text for c in document.tables[0].rows[1].cells][4] == "3"
    assert render_barnes_per_animal(Document(), pd.DataFrame({"animal": ["x"]})) is False


# --- robustness: null groups, undefined SEM --------------------------------------------


def _null_group_frame() -> pd.DataFrame:
    return _frame(
        tidy_row("CTL", "Dia_1", "1", encounter=20.0),
        {**tidy_row("x", "Dia_1", "2", encounter=40.0), "group_id": None},
        {**tidy_row("x", "Dia_1", "3", encounter=60.0), "group_id": float("nan")},
        {**_probe_row("4", probe_offset=1, probe_score=2, probe_attempts=2), "group_id": None},
    )


def test_a_null_group_is_its_own_bucket_in_every_aggregate_and_never_raises():
    df = _null_group_frame()

    curves = learning_curves(df)
    strategies = strategy_distribution(df)
    probes = probe_comparison(df)

    assert list(dict.fromkeys(curves["group"])) == ["CTL", "(no group)"]
    point = _curve(curves, "(no group)", "Dia_1", "encounter_latency_s")
    assert point["n"] == 2
    assert point["mean"] == pytest.approx(50.0)
    assert _curve(curves, "CTL", "Dia_1", "encounter_latency_s")["n"] == 1
    assert set(strategies["group"]) == {"CTL", "(no group)"}
    assert set(probes["group"]) == {"(no group)"}
    assert set(barnes_sheets(df)) == {
        "barnes_learning_curves",
        "barnes_strategy",
        "barnes_probe",
    }


def test_the_word_section_and_figures_survive_a_null_group():
    df = _null_group_frame()
    document = Document()

    render_barnes_aggregates(document, df)

    assert "(no group)" in _text(document)
    assert learning_curve_figure(learning_curves(df)) is not None
    assert strategy_figure(strategy_distribution(df)) is not None
    assert probe_figure(probe_comparison(df)) is not None


def test_a_frame_without_null_groups_is_returned_untouched():
    df = _frame(tidy_row("CTL", "Dia_1", "1"))

    from zebtrack.analysis.reporters.barnes_aggregates import _label_groups

    assert _label_groups(df, "group_id") is df
    assert _label_groups(df, "no_such_column") is df


def _error_bars(figure) -> list[int]:
    from matplotlib.container import ErrorbarContainer

    return [sum(isinstance(c, ErrorbarContainer) for c in ax.containers) for ax in figure.axes]


def test_the_curve_draws_no_error_bar_where_the_sem_is_undefined():
    one_trial = _frame(tidy_row("CTL", "Dia_1", "1"), tidy_row("CTL", "Dia_2", "1"))
    two_trials = _frame(
        tidy_row("CTL", "Dia_1", "1", encounter=20.0),
        tidy_row("CTL", "Dia_1", "2", encounter=40.0),
        tidy_row("CTL", "Dia_2", "1"),
    )

    undefined = learning_curve_figure(learning_curves(one_trial))
    partly = learning_curve_figure(learning_curves(two_trials))

    assert undefined is not None
    assert partly is not None
    assert _error_bars(undefined) == [0, 0, 0, 0]  # n=1 everywhere: no SEM, no bar
    assert _error_bars(partly) == [1, 1, 1, 1]  # only the n=2 point has one


def test_the_probe_figure_has_no_error_bar_for_a_single_probe_and_no_bar_for_no_data():
    one = _frame(_probe_row("1", probe_offset=1, probe_score=2, probe_attempts=2))
    figure = probe_figure(probe_comparison(one))

    assert figure is not None
    assert _error_bars(figure) == [0, 0]

    two = _frame(
        _probe_row("1", probe_offset=1, probe_score=2, probe_attempts=2),
        _probe_row("2", probe_offset=3, probe_score=4, probe_attempts=3),
    )
    figure = probe_figure(probe_comparison(two))
    assert figure is not None
    assert _error_bars(figure) == [1, 1]

    # a probe group with no value for the plotted metric draws no bar at all
    empty = pd.DataFrame(
        {
            "group": ["A"],
            "metric": ["first_hole_score"],
            "n": [0],
            "mean": [np.nan],
            "sem": [np.nan],
        }
    )
    figure = probe_figure(empty)
    assert figure is not None
    heights = [p.get_height() for p in figure.axes[0].patches if isinstance(p, Rectangle)]
    assert all(np.isnan(h) for h in heights)
