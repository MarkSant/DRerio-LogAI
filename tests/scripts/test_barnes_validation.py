"""``scripts/barnes_validation.py`` — validation and calibration against the lab's scoring (#633).

Synthetic data only: no real lab spreadsheet or video is in the repository. The statistics are
checked against values worked out by hand or published (Shrout & Fleiss 1979 for the ICC);
matching, censoring and calibration are checked on small frames whose answer is known; the
recompute mode runs the REAL analysis on a scripted rat (``barnes_builders``).
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import pytest
import yaml
from tests.analysis.protocols.barnes.barnes_builders import FPS, BarnesTable, RatScript

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import barnes_validation as bv  # noqa: E402

pytestmark = pytest.mark.unit


# --- helpers ----------------------------------------------------------------------------------


def app_frame(*rows: dict[str, Any]) -> pd.DataFrame:
    """Canonical app frame from partial rows (missing columns blank)."""
    frame = pd.DataFrame(list(rows))
    for column in bv.APP_COLUMNS:
        if column not in frame.columns:
            frame[column] = np.nan if column in bv._APP_NUMERIC else None
    return bv.coerce_app_frame(frame[list(bv.APP_COLUMNS)])


def lab_frame(*rows: dict[str, Any]) -> pd.DataFrame:
    frame = pd.DataFrame(list(rows))
    frame.insert(0, "source_row", range(2, 2 + len(frame)))
    return frame


# --- statistics: known values -----------------------------------------------------------------


def test_icc_matches_the_published_shrout_fleiss_example():
    """Shrout & Fleiss (1979) Table 2: ICC(2,1) = .29, 95 % CI [.019, .761] (SPSS)."""
    data = np.array(
        [[9, 2, 5, 8], [6, 1, 3, 2], [8, 4, 6, 8], [7, 1, 2, 6], [10, 5, 6, 9], [6, 2, 4, 7]],
        dtype=float,
    )

    result = bv.icc_2_1_matrix(data)

    assert result.n == 6
    assert result.icc == pytest.approx(0.2898, abs=5e-4)
    assert result.ci_lower == pytest.approx(0.019, abs=1e-3)
    assert result.ci_upper == pytest.approx(0.761, abs=1e-3)


def test_icc_is_absolute_agreement_so_a_constant_offset_lowers_it():
    """app = lab + 2 with no noise: consistency would be 1, absolute agreement is 5/9."""
    lab = [1, 2, 3, 4, 5]
    app = [3, 4, 5, 6, 7]

    assert bv.icc_2_1(app, lab).icc == pytest.approx(5 / 9)
    assert bv.icc_2_1(lab, lab).icc == pytest.approx(1.0)


def test_icc_is_undefined_below_three_pairs_and_ignores_nan_pairs():
    assert math.isnan(bv.icc_2_1([1, 2], [1, 2]).icc)
    with_nan = bv.icc_2_1([1, 2, 3, 4, 5, math.nan], [1, 2, 3, 4, 5, 9])
    assert with_nan.n == 5


def test_bland_altman_on_a_worked_example():
    """diff = app - lab = [1, 0, 1, -2]: bias 0, sd sqrt(2), limits ±1.96·sqrt(2), MAD 1."""
    result = bv.bland_altman([10, 12, 14, 16], [9, 12, 13, 18])

    assert result.n == 4
    assert result.bias == pytest.approx(0.0)
    assert result.sd_diff == pytest.approx(math.sqrt(2))
    assert result.loa_upper == pytest.approx(1.96 * math.sqrt(2))
    assert result.loa_lower == pytest.approx(-1.96 * math.sqrt(2))
    assert result.mean_abs_diff == pytest.approx(1.0)
    # t(0.975, 3) = 3.1824; half-width = 3.1824 * sd / sqrt(n)
    assert result.bias_ci_upper == pytest.approx(3.1824 * math.sqrt(2) / 2, abs=1e-3)


def test_bland_altman_sign_is_app_minus_lab():
    assert bv.bland_altman([5, 6, 7], [3, 4, 5]).bias == pytest.approx(2.0)


def test_bland_altman_degenerate_inputs():
    empty = bv.bland_altman([], [])
    one = bv.bland_altman([4.0], [3.0])

    assert empty.n == 0 and math.isnan(empty.bias)
    assert one.n == 1 and one.bias == pytest.approx(1.0) and math.isnan(one.sd_diff)


def test_paired_rejects_series_of_different_length():
    with pytest.raises(ValueError, match="differ in length"):
        bv.bland_altman([1, 2, 3], [1, 2])


def test_cohen_kappa_on_the_classic_two_by_two():
    """Lab a/b vs app a/b: [[20, 10], [5, 15]], p_o = .7, p_e = .5, kappa = .4."""
    lab = ["a"] * 30 + ["b"] * 20
    app = ["a"] * 20 + ["b"] * 10 + ["a"] * 5 + ["b"] * 15

    result = bv.cohen_kappa(app, lab, labels=("a", "b"))

    assert result.matrix == ((20, 10), (5, 15))  # rows = lab, columns = app
    assert result.observed_agreement == pytest.approx(0.7)
    assert result.kappa == pytest.approx(0.4)
    assert result.ci_lower < result.kappa < result.ci_upper


def test_cohen_kappa_three_strategies_and_its_confusion_matrix_orientation():
    lab = ["direct", "direct", "serial", "serial", "random", "random"]
    app = ["direct", "serial", "serial", "serial", "random", "direct"]

    result = bv.cohen_kappa(app, lab)

    assert result.labels == ("direct", "serial", "random")
    assert result.matrix == ((1, 1, 0), (0, 2, 0), (1, 0, 1))
    assert result.observed_agreement == pytest.approx(4 / 6)
    assert result.kappa == pytest.approx(0.5)


def test_cohen_kappa_is_undefined_when_both_raters_use_one_label():
    result = bv.cohen_kappa(["random"] * 4, ["random"] * 4)

    assert result.observed_agreement == 1.0
    assert math.isnan(result.kappa)


def test_cohen_kappa_ignores_labels_outside_the_label_set():
    result = bv.cohen_kappa(["direct", "weird"], ["direct", "direct"])

    assert result.n == 1


def test_exact_agreement_and_spearman():
    assert bv.exact_agreement([1, 2, 3, 4], [1, 2, 4, 4]) == pytest.approx(0.75)
    assert math.isnan(bv.exact_agreement([], []))
    rho, p_value = bv.spearman([1, 2, 3, 4, 5], [10, 20, 30, 40, 50])
    assert rho == pytest.approx(1.0) and p_value < 0.01
    assert all(math.isnan(v) for v in bv.spearman([1, 1, 1], [1, 2, 3]))
    assert all(math.isnan(v) for v in bv.spearman([1, 2], [1, 2]))


def test_start_offset_distribution_on_known_offsets():
    """app - manual = [-1, 0, 0.5, 2]: the app starts earlier when negative."""
    result = bv.start_offset_distribution([9.0, 10.0, 10.5, 12.0], [10.0, 10.0, 10.0, 10.0])

    assert result.n == 4
    assert result.mean == pytest.approx(0.375)
    assert result.median == pytest.approx(0.25)
    assert (result.minimum, result.maximum) == (-1.0, 2.0)
    assert result.within_0_5_s == pytest.approx(0.5)  # |0|, |0.5|
    assert result.within_1_s == pytest.approx(0.75)
    assert result.within_2_s == pytest.approx(1.0)


def test_count_block_reports_exact_within_one_and_bias():
    block = bv.count_block([2, 3, 5, 0], [2, 4, 5, 3])

    assert block["n"] == 4
    assert block["exact_agreement"] == pytest.approx(0.5)
    assert block["within_1"] == pytest.approx(0.75)
    assert block["mad"] == pytest.approx(1.0)
    assert block["bias"] == pytest.approx(-1.0)


# --- censoring --------------------------------------------------------------------------------


def _latency_case():
    lab = pd.Series([10.0, 20.0, 30.0, 240.0, 15.0, 240.0])
    app = pd.Series([11.0, 18.0, 33.0, 240.0, 240.0, 200.0])
    lab_cens = pd.Series([False, False, False, True, False, True])
    app_cens = pd.Series([False, False, False, True, True, False])
    return bv.latency_comparison(app, app_cens, lab, lab_cens)


def test_censored_pairs_are_not_observations():
    result = _latency_case()

    assert result["counts"] == {
        "pairs": 6,
        "lab_missing": 0,
        "app_missing": 0,
        "compared": 6,
        "both_observed": 3,
    }
    observed = result["observed"]
    assert observed["n"] == 3
    # diffs of the three observed pairs: +1, -2, +3
    assert observed["bland_altman"]["bias"] == pytest.approx(2 / 3)
    assert observed["mad"] == pytest.approx(2.0)


def test_censoring_agreement_is_reported_separately():
    censoring = _latency_case()["censoring"]

    assert censoring["n"] == 6
    assert censoring["both_observed"] == 3
    assert censoring["both_censored"] == 1
    assert censoring["lab_only_censored"] == 1  # lab 240, app observed 200
    assert censoring["app_only_censored"] == 1  # app 240, lab observed 15
    assert censoring["agreement"] == pytest.approx(4 / 6)


def test_ceiling_imputed_view_keeps_the_censored_pairs_and_is_labelled_apart():
    result = _latency_case()

    assert result["ceiling_imputed"]["n"] == 6
    assert result["ceiling_imputed"]["n"] != result["observed"]["n"]
    # The pair (app 240, lab 15) alone adds +225 to the imputed bias.
    assert result["ceiling_imputed"]["bland_altman"]["bias"] > 30


def test_blank_values_are_counted_as_missing_not_compared():
    lab = pd.Series([10.0, math.nan, 30.0, 240.0])
    app = pd.Series([11.0, 12.0, math.nan, 240.0])
    lab_cens = pd.Series([False, False, False, True])
    app_cens = pd.Series([False, False, None, True], dtype=object)

    result = bv.latency_comparison(app, app_cens, lab, lab_cens)

    counts = result["counts"]
    assert (counts["lab_missing"], counts["app_missing"]) == (1, 1)
    assert counts["compared"] == 2
    assert counts["both_observed"] == 1


def test_a_lab_censored_row_without_a_value_still_compares_its_flag():
    lab = pd.Series([math.nan, 10.0])
    app = pd.Series([240.0, 11.0])
    result = bv.latency_comparison(app, pd.Series([True, False]), lab, pd.Series([True, False]))

    assert result["counts"]["compared"] == 2
    assert result["censoring"]["both_censored"] == 1
    assert result["observed"]["n"] == 1


# --- cell and identifier parsing --------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (83.5, 83.5),
        ("83,5", 83.5),
        ("1:23.5", 83.5),
        ("0:01:23", 83.0),
        ("12s", 12.0),
        ("  7 ", 7.0),
        ("", math.nan),
        ("n/a", math.nan),
        (None, math.nan),
        (float("nan"), math.nan),
        (True, math.nan),
    ],
)
def test_parse_seconds(raw, expected):
    result = bv.parse_seconds(raw)

    assert (math.isnan(result) and math.isnan(expected)) or result == pytest.approx(expected)


def test_parse_seconds_accepts_excel_time_and_duration_objects():
    import datetime as dt

    assert bv.parse_seconds(dt.time(0, 1, 30)) == pytest.approx(90.0)
    assert bv.parse_seconds(dt.timedelta(seconds=75)) == pytest.approx(75.0)
    assert bv.parse_seconds(pd.Timedelta(seconds=5)) == pytest.approx(5.0)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Dia_1", "1"),
        ("dia 01", "1"),
        (1, "1"),
        (1.0, "1"),
        ("Grupo_CBD", "cbd"),
        ("  Controle ", "controle"),
        ("Sujeito 12", "12"),
        ("Á_é", "a_e"),
        ("", None),
        (None, None),
        (float("nan"), None),
    ],
)
def test_normalize_token(raw, expected):
    assert bv.normalize_token(raw) == expected


def test_path_parts_handles_both_separators_drive_letters_and_the_extension():
    assert bv.path_parts("C:\\lab\\Dia_2\\CECT_4\\CECT_4.mp4") == (
        "lab",
        "dia_2",
        "cect_4",
        "cect_4",
    )
    assert bv.path_parts("lab/Dia_2/CECT_4/CECT_4.MP4") == ("lab", "dia_2", "cect_4", "cect_4")
    assert bv.path_parts(None) == ()


def test_parse_flag():
    assert bv.parse_flag("Sim") is True
    assert bv.parse_flag("nao") is False
    assert bv.parse_flag(1) is True
    assert bv.parse_flag(0.0) is False
    assert bv.parse_flag("talvez") is None
    assert bv.parse_flag(None) is None


def test_jsonable_unwraps_numpy_and_drops_non_finite():
    payload = {"a": np.float64(1.5), "b": np.int64(2), "c": float("nan"), "d": [np.bool_(True)]}

    assert json.dumps(bv.jsonable(payload)) == '{"a": 1.5, "b": 2, "c": null, "d": [true]}'


# --- the mapping file -------------------------------------------------------------------------


def _write_mapping(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "mapping.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def test_the_documented_example_mapping_parses(tmp_path):
    path = tmp_path / "example.yaml"
    assert bv.run(["init-mapping", "--out", str(path)]) == 0

    mapping = bv.load_mapping(path)

    assert set(mapping.sheets) == {"latencies", "strategy", "probe"}
    assert mapping.match.keys == ("group", "day", "subject")
    assert mapping.sheets["latencies"].censor_at_s == 240.0
    assert mapping.sheets["latencies"].file == (tmp_path / "latencias.xlsx").resolve()
    assert mapping.sheets["strategy"].label_map["aleatoria"] == "random"
    assert mapping.match.aliases["group"] == {"controle": "ctrl"}


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("sheets: {foo: {file: a.csv, columns: {subject: S}}}", "unknown sheet"),
        ("sheets: {latencies: {columns: {subject: S, entry_latency_s: E}}}", "file is required"),
        (
            "sheets: {latencies: {file: a.csv, columns: {subject: S, bogus: B}}}",
            "unknown fields",
        ),
        (
            "sheets: {latencies: {file: a.csv, columns: {entry_latency_s: E}}}",
            "identify rows",
        ),
        ("sheets: {latencies: {file: a.csv, columns: {subject: S}}}", "at least one of"),
        (
            "sheets: {strategy: {file: a.csv, columns: {subject: S, strategy: T},"
            " label_map: {x: weird}}}",
            "label_map",
        ),
        (
            "match: {keys: [group, color]}\n"
            "sheets: {strategy: {file: a.csv, columns: {subject: S, strategy: T}}}",
            "group/day/subject",
        ),
        ("sheets: {}", "non-empty"),
        ("- not a mapping", "object"),
    ],
)
def test_invalid_mapping_files_say_what_is_wrong(tmp_path, body, message):
    with pytest.raises(bv.ValidationInputError, match=message):
        bv.load_mapping(_write_mapping(tmp_path, body))


def test_a_json_mapping_is_accepted(tmp_path):
    path = tmp_path / "m.json"
    path.write_text(
        json.dumps(
            {
                "sheets": {
                    "strategy": {"file": "s.csv", "columns": {"subject": "S", "strategy": "T"}}
                }
            }
        ),
        encoding="utf-8",
    )

    assert "strategy" in bv.load_mapping(path).sheets


# --- reading the lab's sheets -----------------------------------------------------------------


def _latencies_spec(tmp_path: Path, file: str = "lat.csv", **extra: Any) -> bv.SheetSpec:
    columns = {
        "group": "Grupo",
        "day": "Dia",
        "subject": "Animal",
        "start_time_s": "Inicio",
        "encounter_latency_s": "Latencia encontro (s)",
        "entry_latency_s": "Latencia entrada (s)",
        "primary_errors": "Erros primarios",
    }
    columns.update(extra.pop("columns", {}))
    return bv.SheetSpec(
        name="latencies",
        file=tmp_path / file,
        sheet=None,
        header_row=1,
        columns=columns,
        censor_at_s=extra.pop("censor_at_s", 240.0),
        label_map=dict(bv._DEFAULT_STRATEGY_MAP),
    )


def test_a_csv_sheet_is_read_into_canonical_columns_with_the_lab_censoring_rule(tmp_path):
    (tmp_path / "lat.csv").write_text(
        "Grupo;Dia;Animal;Inicio;Latencia encontro (s);Latencia entrada (s);Erros primarios\n"
        "CBD;1;7;0:05;12,5;40;3\n"
        "CBD;1;8;0:07;240;240;9\n"
        "CTRL;2;1;;55;abc;0\n",
        encoding="utf-8",
    )

    table, notes = bv.read_lab_sheet(_latencies_spec(tmp_path))

    assert table["source_row"].tolist() == [2, 3, 4]
    assert table["start_time_s"].tolist()[:2] == [5.0, 7.0]
    assert math.isnan(table["start_time_s"].iloc[2])
    assert table["encounter_latency_s"].tolist() == [12.5, 240.0, 55.0]
    assert table["entry_censored"].tolist() == [False, True, False]  # >= ceiling; 'abc' is blank
    assert table["encounter_censored"].tolist() == [False, True, False]
    assert table["primary_errors"].tolist() == [3.0, 9.0, 0.0]
    assert notes == ["latencies row 4: 'Latencia entrada (s)' is not a time; left blank"]


def test_an_explicit_yes_no_column_also_marks_censoring(tmp_path):
    (tmp_path / "lat.csv").write_text(
        "Grupo,Dia,Animal,Inicio,Latencia encontro (s),Latencia entrada (s),"
        "Erros primarios,Nao entrou\n"
        "A,1,1,1,10,100,0,sim\n"
        "A,1,2,1,10,100,0,nao\n",
        encoding="utf-8",
    )
    spec = _latencies_spec(tmp_path, columns={"entry_censored": "Nao entrou"})

    table, _notes = bv.read_lab_sheet(spec)

    assert table["entry_censored"].tolist() == [True, False]


def test_a_custom_censoring_ceiling_is_honoured(tmp_path):
    (tmp_path / "lat.csv").write_text(
        "Grupo,Dia,Animal,Inicio,Latencia encontro (s),Latencia entrada (s),Erros primarios\n"
        "A,1,1,1,10,180,0\n",
        encoding="utf-8",
    )

    table, _ = bv.read_lab_sheet(_latencies_spec(tmp_path, censor_at_s=180.0))

    assert table["entry_censored"].tolist() == [True]


def test_an_xlsx_sheet_with_accented_and_differently_cased_headers(tmp_path):
    pd.DataFrame(
        {
            "grupo": ["A"],
            "DIA": [1],
            "Animal": [3],
            "Início": ["0:10"],
            "Latência encontro (s)": [20.0],
            "Latência entrada (s)": [35.0],
            "Erros primários": [2],
        }
    ).to_excel(tmp_path / "lat.xlsx", index=False)
    spec = _latencies_spec(
        tmp_path,
        file="lat.xlsx",
        columns={"start_time_s": "Inicio", "primary_errors": "Erros primarios"},
    )

    table, notes = bv.read_lab_sheet(spec)

    assert notes == []
    assert table.loc[0, "encounter_latency_s"] == 20.0
    assert table.loc[0, "start_time_s"] == 10.0
    assert table.loc[0, "primary_errors"] == 2.0


def test_a_header_row_below_the_first_is_honoured(tmp_path):
    (tmp_path / "lat.csv").write_text(
        "titulo da planilha,,\nAnimal,Latencia entrada (s),Grupo\n7,30,CBD\n", encoding="utf-8"
    )
    spec = bv.SheetSpec(
        name="latencies",
        file=tmp_path / "lat.csv",
        sheet=None,
        header_row=2,
        columns={"subject": "Animal", "entry_latency_s": "Latencia entrada (s)"},
        censor_at_s=240.0,
        label_map={},
    )

    table, _ = bv.read_lab_sheet(spec)

    assert table["entry_latency_s"].tolist() == [30.0]
    assert table["source_row"].tolist() == [3]


def test_a_missing_column_lists_the_headers_the_sheet_has(tmp_path):
    (tmp_path / "lat.csv").write_text("Animal,Outra\n1,2\n", encoding="utf-8")

    with pytest.raises(bv.ValidationInputError, match=r"Grupo.*not found.*\['Animal', 'Outra'\]"):
        bv.read_lab_sheet(_latencies_spec(tmp_path))


def test_a_missing_file_and_an_unsupported_type_are_input_errors(tmp_path):
    with pytest.raises(bv.ValidationInputError, match="file not found"):
        bv.read_lab_sheet(_latencies_spec(tmp_path, file="nope.csv"))
    (tmp_path / "x.doc").write_text("hi", encoding="utf-8")
    with pytest.raises(bv.ValidationInputError, match="unsupported file type"):
        bv.read_lab_sheet(_latencies_spec(tmp_path, file="x.doc"))


def test_strategy_labels_are_mapped_and_unmapped_ones_are_reported(tmp_path):
    (tmp_path / "s.csv").write_text(
        "Animal,Estrategia\n1,Direta\n2,Seriada\n3,Aleatória\n4,mista\n5,\n", encoding="utf-8"
    )
    spec = bv.SheetSpec(
        name="strategy",
        file=tmp_path / "s.csv",
        sheet=None,
        header_row=1,
        columns={"subject": "Animal", "strategy": "Estrategia"},
        censor_at_s=240.0,
        label_map={**bv._DEFAULT_STRATEGY_MAP, "mista": "random"},
    )

    table, notes = bv.read_lab_sheet(spec)

    assert table["strategy"].tolist() == ["direct", "serial", "random", "random", None]
    assert notes == []
    # without the user's extra label the unknown one is reported, row kept blank
    spec_default = bv.SheetSpec(**{**spec.__dict__, "label_map": dict(bv._DEFAULT_STRATEGY_MAP)})
    table2, notes2 = bv.read_lab_sheet(spec_default)
    assert table2["strategy"].tolist()[3] is None
    assert notes2 == ["strategy row 5: strategy 'mista' is not in the label map"]


# --- matching ---------------------------------------------------------------------------------


def test_rows_match_by_group_day_subject_after_normalisation():
    lab = lab_frame(
        {"group": "Grupo_CBD", "day": "Dia 1", "subject": "07"},
        {"group": "cbd", "day": 2, "subject": 7.0},
    )
    app = app_frame(
        {"group": "cbd", "day": "1", "subject": "7"},
        {"group": "CBD", "day": "Dia_2", "subject": "Sujeito_7"},
    )

    result = bv.match_rows(lab, app, bv.MatchSpec())

    assert result.pairs == [(0, 0), (1, 1)]
    assert result.lab_unmatched == [] and result.app_unmatched == []
    assert set(result.rules.values()) == {"key"}


def test_unmatched_rows_are_listed_on_both_sides():
    lab = lab_frame(
        {"group": "A", "day": 1, "subject": 1},
        {"group": "A", "day": 1, "subject": 99},
    )
    app = app_frame(
        {"group": "A", "day": 1, "subject": 1},
        {"group": "A", "day": 1, "subject": 2},
    )

    result = bv.match_rows(lab, app, bv.MatchSpec())

    assert result.pairs == [(0, 0)]
    assert result.lab_unmatched == [1]
    assert result.app_unmatched == [1]
    summary = bv.match_summary(lab, app, result)
    assert summary["lab_unmatched"][0]["subject"] == 99
    assert str(summary["app_unmatched"][0]["subject"]) == "2"


def test_a_key_with_a_blank_part_cannot_match():
    lab = lab_frame({"group": "A", "day": None, "subject": 1})
    app = app_frame({"group": "A", "day": 1, "subject": 1})

    assert bv.match_rows(lab, app, bv.MatchSpec()).lab_unmatched == [0]


def test_aliases_translate_the_lab_spelling():
    lab = lab_frame({"group": "controle", "day": 1, "subject": 1})
    app = app_frame({"group": "ctrl", "day": 1, "subject": 1})
    spec = bv.MatchSpec(aliases={"group": {"controle": "ctrl"}})

    assert bv.match_rows(lab, app, spec).pairs == [(0, 0)]
    assert bv.match_rows(lab, app, bv.MatchSpec()).pairs == []


def test_the_same_subject_on_two_days_is_ambiguous_without_a_day_key_not_silently_matched():
    lab = lab_frame({"group": "A", "subject": 4})
    app = app_frame(
        {"group": "A", "day": 1, "subject": 4},
        {"group": "A", "day": 2, "subject": 4},
    )

    result = bv.match_rows(lab, app, bv.MatchSpec(keys=("group", "day", "subject")))

    assert result.pairs == []
    assert len(result.ambiguous) == 1
    assert result.ambiguous[0]["reason"] == "several app rows fit"


def test_a_video_path_separates_the_same_file_name_on_two_days():
    lab = lab_frame({"video": "D:\\lab\\Dia_2\\CECT_4\\CECT_4.mp4"})
    app = app_frame(
        {"video_path": "C:/proj/Dia_1/CECT_4/CECT_4.mp4", "experiment_id": "CECT_4"},
        {"video_path": "C:/proj/Dia_2/CECT_4/CECT_4.mp4", "experiment_id": "CECT_4"},
    )

    result = bv.match_rows(lab, app, bv.MatchSpec())

    assert result.pairs == [(0, 1)]
    assert result.rules[0] == "video_path"


def test_a_bare_file_name_is_never_enough_by_default():
    lab = lab_frame({"video": "CECT_4.mp4"})
    app = app_frame(
        {"video_path": "C:/proj/Dia_1/CECT_4/CECT_4.mp4"},
        {"video_path": "C:/proj/Dia_2/CECT_4/CECT_4.mp4"},
    )

    result = bv.match_rows(lab, app, bv.MatchSpec())

    assert result.pairs == []
    assert result.lab_unmatched == [0]


def test_a_unique_basename_matches_only_when_allowed_and_unique_on_both_sides():
    lab = lab_frame({"video": "rat9.mp4"}, {"video": "CECT_4.mp4"})
    app = app_frame(
        {"video_path": "C:/proj/rat9/rat9.mp4", "experiment_id": "rat9"},
        {"video_path": "C:/proj/Dia_1/CECT_4/CECT_4.mp4", "experiment_id": "CECT_4"},
        {"video_path": "C:/proj/Dia_2/CECT_4/CECT_4.mp4", "experiment_id": "CECT_4"},
    )

    off = bv.match_rows(lab, app, bv.MatchSpec())
    on = bv.match_rows(lab, app, bv.MatchSpec(allow_unique_basename=True))

    assert off.pairs == []
    assert on.pairs == [(0, 0)]
    assert on.rules[0] == "basename"
    assert [a["reason"] for a in on.ambiguous] == ["the file name is not unique"]


def test_two_lab_rows_claiming_one_app_row_are_both_refused():
    lab = lab_frame(
        {"group": "A", "day": 1, "subject": 1},
        {"group": "A", "day": 1, "subject": 1},
    )
    app = app_frame({"group": "A", "day": 1, "subject": 1})

    result = bv.match_rows(lab, app, bv.MatchSpec())

    assert result.pairs == []
    assert [a["reason"] for a in result.ambiguous] == [
        "several lab rows claim the same app row"
    ] * 2
    assert result.app_unmatched == [0]


# --- one sheet, end to end (frames) -----------------------------------------------------------


def _latency_world():
    lab = lab_frame(
        *[
            {
                "group": "A",
                "day": 1,
                "subject": i,
                "start_time_s": 10.0,
                "encounter_latency_s": enc,
                "encounter_censored": enc >= 240,
                "entry_latency_s": ent,
                "entry_censored": ent >= 240,
                "primary_errors": err,
            }
            for i, (enc, ent, err) in enumerate(
                [(10.0, 20.0, 1), (30.0, 60.0, 4), (50.0, 240.0, 2), (240.0, 240.0, 6)], start=1
            )
        ]
    )
    app = app_frame(
        *[
            {
                "group": "A",
                "day": 1,
                "subject": i,
                "status": "ok",
                "t_start_s": 10.5,
                "encounter_latency_s": enc,
                "encounter_censored": enc >= 240,
                "entry_latency_s": ent,
                "entry_censored": ent >= 240,
                "primary_errors": err,
            }
            for i, (enc, ent, err) in enumerate(
                [(11.0, 22.0, 1), (29.0, 64.0, 5), (52.0, 240.0, 2), (240.0, 150.0, 6)], start=1
            )
        ]
    )
    return lab, app


def test_evaluate_a_latency_sheet_end_to_end():
    lab, app = _latency_world()
    lab_tables = {"latencies": lab}

    result = bv.evaluate(lab_tables, app, bv.match_all(lab_tables, app, bv.MatchSpec()))

    block = result.summary["latencies"]
    assert block["matching"]["matched"] == 4
    assert block["encounter"]["counts"]["both_observed"] == 3
    # observed encounter diffs (app - lab): +1, -1, +2
    assert block["encounter"]["observed"]["bland_altman"]["bias"] == pytest.approx(2 / 3)
    # entry: observed pairs (20, 22), (60, 64): diffs +2, +4; the last pair is lab 240 vs app 150
    assert block["entry"]["observed"]["n"] == 2
    assert block["entry"]["observed"]["bland_altman"]["bias"] == pytest.approx(3.0)
    assert block["entry"]["censoring"]["lab_only_censored"] == 1
    assert block["entry"]["censoring"]["both_censored"] == 1
    assert block["primary_errors"]["exact_agreement"] == pytest.approx(0.75)
    assert block["start_offset"]["mean"] == pytest.approx(0.5)
    assert block["app_status"] == {"ok": 4}
    pairs = result.pair_tables["latencies"]
    assert {"lab_entry_latency_s", "app_entry_latency_s", "lab_row"} <= set(pairs.columns) | {
        "lab_row"
    }
    assert len(pairs) == 4


def test_strategy_compares_the_automatic_strategy_never_the_manual_correction():
    lab = lab_frame(
        {"group": "A", "day": 1, "subject": 1, "strategy": "direct"},
        {"group": "A", "day": 1, "subject": 2, "strategy": "serial"},
        {"group": "A", "day": 1, "subject": 3, "strategy": "random"},
        {"group": "A", "day": 1, "subject": 4, "strategy": None},
    )
    app = app_frame(
        # subject 1: auto says random, but a manual correction (copied from the lab) says direct
        {"group": "A", "day": 1, "subject": 1, "strategy_auto": "random", "strategy": "direct"},
        {"group": "A", "day": 1, "subject": 2, "strategy_auto": "serial", "strategy": "serial"},
        {"group": "A", "day": 1, "subject": 3, "strategy_auto": "random", "strategy": "random"},
        {"group": "A", "day": 1, "subject": 4, "strategy_auto": "serial", "strategy": "serial"},
    )
    tables = {"strategy": lab}

    block = bv.evaluate(tables, app, bv.match_all(tables, app, bv.MatchSpec())).summary["strategy"]

    strategy = block["strategy"]
    assert strategy["counts"] == {"pairs": 4, "lab_missing": 1, "app_missing": 0, "compared": 3}
    assert strategy["kappa"]["matrix"] == ((0, 0, 1), (0, 1, 0), (0, 0, 1))
    assert strategy["kappa"]["observed_agreement"] == pytest.approx(2 / 3)


def test_probe_sheet_score_attempts_and_first_error_presence():
    lab = lab_frame(
        {
            "group": "A",
            "day": 1,
            "subject": 1,
            "probe_score": 1,
            "first_error_latency_s": math.nan,
            "attempts": 1,
        },
        {
            "group": "A",
            "day": 1,
            "subject": 2,
            "probe_score": 4,
            "first_error_latency_s": 12.0,
            "attempts": 3,
        },
        {
            "group": "A",
            "day": 1,
            "subject": 3,
            "probe_score": 10,
            "first_error_latency_s": 5.0,
            "attempts": 6,
        },
        {
            "group": "A",
            "day": 1,
            "subject": 4,
            "probe_score": 2,
            "first_error_latency_s": 8.0,
            "attempts": 2,
        },
    )
    app = app_frame(
        {
            "group": "A",
            "day": 1,
            "subject": 1,
            "probe_first_hole_score": 1,
            "probe_attempts_to_target": 1,
        },
        {
            "group": "A",
            "day": 1,
            "subject": 2,
            "probe_first_hole_score": 4,
            "probe_first_error_latency_s": 14.0,
            "probe_attempts_to_target": 3,
        },
        {
            "group": "A",
            "day": 1,
            "subject": 3,
            "probe_first_hole_score": 9,
            "probe_first_error_latency_s": 5.0,
            "probe_attempts_to_target": 7,
        },
        {
            "group": "A",
            "day": 1,
            "subject": 4,
            "probe_first_hole_score": 2,
            "probe_attempts_to_target": 2,
        },
    )
    tables = {"probe": lab}

    block = bv.evaluate(tables, app, bv.match_all(tables, app, bv.MatchSpec())).summary["probe"]

    assert block["score"]["exact_agreement"] == pytest.approx(0.75)
    assert block["attempts"]["exact_agreement"] == pytest.approx(0.75)
    assert block["first_error_latency"]["missing"] == {
        "both_present": 2,
        "both_blank": 1,
        "lab_only": 1,
        "app_only": 0,
    }
    assert block["first_error_latency"]["agreement"]["bland_altman"]["bias"] == pytest.approx(1.0)


def test_rows_the_app_could_not_compute_are_visible_as_a_status_not_a_silent_drop():
    lab, app = _latency_world()
    app.loc[1, ["status", "encounter_latency_s", "entry_latency_s", "primary_errors"]] = [
        "unavailable:layout_unresolved",
        math.nan,
        math.nan,
        math.nan,
    ]
    tables = {"latencies": lab}

    block = bv.evaluate(tables, app, bv.match_all(tables, app, bv.MatchSpec())).summary["latencies"]

    assert block["app_status"] == {"ok": 3, "unavailable:layout_unresolved": 1}
    assert block["encounter"]["counts"]["app_missing"] == 1


def test_evaluate_can_be_restricted_to_a_subset_of_app_rows():
    lab, app = _latency_world()
    tables = {"latencies": lab}
    matches = bv.match_all(tables, app, bv.MatchSpec())

    subset = bv.evaluate(tables, app, matches, only_app_rows=[0, 1]).summary["latencies"]

    assert subset["pairs"] == 2
    assert subset["matching"] == {"lab_rows": 4, "matched": 2}


# --- the app's unified summary ----------------------------------------------------------------


def _unified_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "group": ["A", "A"],
            "day": ["Dia_1", "Dia_1"],
            "subject": ["1", "2"],
            "experiment_id": ["r1", "r2"],
            "barnes_status": ["ok", "unavailable"],
            "barnes_trial_type": ["training", None],
            "window_start_s": [10.0, None],
            "barnes_encounter_latency_s": [12.0, None],
            "barnes_encounter_censored": [False, None],
            "barnes_entry_latency_s": [240.0, None],
            "barnes_entry_censored": [True, None],
            "barnes_primary_errors": [2, None],
            "barnes_strategy_auto": ["serial", None],
        }
    )


def test_read_unified_maps_the_raw_columns_and_notes_the_missing_ones(tmp_path):
    _unified_frame().to_parquet(tmp_path / "unified_summary_20260101_000000_000000.parquet")

    app, notes = bv.read_unified(tmp_path / "unified_summary_20260101_000000_000000.parquet")

    assert app.loc[0, "status"] == "ok"
    assert app.loc[0, "encounter_latency_s"] == 12.0
    assert app.loc[0, "entry_censored"] is True
    assert app.loc[1, "encounter_censored"] is None
    assert app.loc[0, "t_start_s"] == 10.0
    assert app.loc[0, "strategy_auto"] == "serial"
    assert any("barnes_probe_first_hole_score" in n for n in notes)
    assert any("video_path" in n for n in notes)


def test_read_unified_takes_the_newest_file_of_a_folder_and_honours_overrides(tmp_path):
    sub = tmp_path / "unified_reports" / "total"
    sub.mkdir(parents=True)
    old = _unified_frame().assign(barnes_status="old")
    old.to_parquet(sub / "unified_summary_20250101_000000_000000.parquet")
    renamed = _unified_frame().rename(columns={"barnes_status": "Barnes Status"})
    renamed.to_parquet(sub / "unified_summary_20260101_000000_000000.parquet")

    app, _ = bv.read_unified(tmp_path, {"status": "Barnes Status"})

    assert app["status"].tolist() == ["ok", "unavailable"]


def test_read_unified_without_any_file_is_an_input_error(tmp_path):
    with pytest.raises(bv.ValidationInputError, match="no unified"):
        bv.read_unified(tmp_path)


def test_metrics_row_blanks_every_number_when_the_status_is_not_ok():
    unavailable = {"status": "unavailable", "reason": "no_rois", "protocol": "barnes"}

    row = bv.metrics_row(unavailable, window_start_s=None)

    assert row["status"] == "unavailable:no_rois"
    assert math.isnan(row["encounter_latency_s"]) and math.isnan(row["t_start_s"])

    ok = bv.metrics_row(
        {
            "status": "ok",
            "trial_type": "training",
            "encounter_latency_s": 3.0,
            "encounter_censored": False,
            "strategy_auto": "direct",
            "primary_errors": 0,
        },
        window_start_s=1.5,
    )
    assert (ok["status"], ok["t_start_s"], ok["strategy_auto"]) == ("ok", 1.5, "direct")


# --- reports ----------------------------------------------------------------------------------


def _full_result():
    lab, app = _latency_world()
    strat = lab_frame(
        {"group": "A", "day": 1, "subject": 1, "strategy": "direct"},
        {"group": "A", "day": 1, "subject": 2, "strategy": "serial"},
        {"group": "A", "day": 1, "subject": 77, "strategy": "random"},
    )
    app["strategy_auto"] = ["direct", "random", "serial", None]
    tables = {"latencies": lab, "strategy": strat}
    result = bv.evaluate(tables, app, bv.match_all(tables, app, bv.MatchSpec()))
    result.notes = ["a note"]
    return result


def test_the_markdown_report_states_the_conventions_and_lists_unmatched_rows():
    result = _full_result()

    text = bv.render_markdown(result.summary, title="T", notes=result.notes)

    assert "# T" in text and "app - lab" in text
    assert "## Sheet: latencies" in text and "## Sheet: strategy" in text
    assert "Both observed (the figure to quote)" in text
    assert "NOT observations" in text
    assert "Censoring agreement" in text
    assert "ICC(2,1)" in text
    assert "Confusion matrix (rows = lab, columns = app)" in text
    assert "Lab rows with no app counterpart (1)" in text
    assert '"subject": 77' in text
    assert "- a note" in text


def test_write_outputs_creates_the_report_the_workbook_and_the_json(tmp_path):
    result = _full_result()

    paths = bv.write_outputs(tmp_path / "out", result, title="T")

    assert set(paths) == {"report", "workbook", "summary"}
    assert all(p.is_file() for p in paths.values())
    with pd.ExcelFile(paths["workbook"]) as workbook:
        sheets = workbook.sheet_names
    assert {"Summary", "pairs_latencies", "pairs_strategy", "unmatched_strategy"} <= set(sheets)
    summary = pd.read_excel(paths["workbook"], sheet_name="Summary")
    assert list(summary.columns) == ["sheet", "metric", "statistic", "value"]
    payload = json.loads(paths["summary"].read_text(encoding="utf-8"))
    assert payload["summary"]["latencies"]["matching"]["matched"] == 4
    assert payload["notes"] == ["a note"]


# --- calibration: split, grid, loss -----------------------------------------------------------


def _animals(per_group: dict[str, int], videos: int = 2) -> pd.DataFrame:
    """Identity rows: ``per_group[g]`` animals in group g, each with ``videos`` videos (days)."""
    rows = []
    for group, count in per_group.items():
        for subject in range(1, count + 1):
            rows += [
                {"group": group, "day": str(day), "subject": str(subject)}
                for day in range(1, videos + 1)
            ]
    return pd.DataFrame(rows)


def _animal_of(identities: pd.DataFrame, index: int) -> tuple[str, str]:
    row = identities.loc[index]
    return (row["group"], row["subject"])


def test_split_is_by_animal_stratified_by_group_seeded_disjoint_and_complete():
    identities = _animals({"A": 6, "B": 6}, videos=2)
    indexes = list(range(len(identities)))

    cal, held = bv.split_cases(identities, indexes, fraction=0.5, seed=7)
    again = bv.split_cases(identities, indexes, fraction=0.5, seed=7)
    other = bv.split_cases(identities, indexes, fraction=0.5, seed=8)

    assert (cal, held) == again
    assert (cal, held) != other
    assert sorted(cal + held) == indexes and not set(cal) & set(held)
    # the same rat never sits on both sides, whatever the number of its videos
    cal_animals = {_animal_of(identities, i) for i in cal}
    held_animals = {_animal_of(identities, i) for i in held}
    assert not cal_animals & held_animals
    for group in ("A", "B"):  # stratified by group: 3 of 6 animals each side
        assert len({a for a in cal_animals if a[0] == group}) == 3
        assert len({a for a in held_animals if a[0] == group}) == 3


def test_a_group_of_two_animals_keeps_one_on_each_side_and_single_animal_groups_are_pooled():
    identities = _animals({"A": 2, "B": 1, "C": 1, "D": 1, "E": 1}, videos=3)
    indexes = list(range(len(identities)))

    cal, held = bv.split_cases(identities, indexes, fraction=0.6, seed=1)

    cal_animals = {_animal_of(identities, i) for i in cal}
    held_animals = {_animal_of(identities, i) for i in held}
    assert not cal_animals & held_animals
    assert len({a for a in cal_animals if a[0] == "A"}) == 1
    assert len({a for a in held_animals if a[0] == "A"}) == 1
    # four single-animal groups pooled: round(0.6 x 4) = 2 animals to calibration
    assert len({a for a in cal_animals if a[0] != "A"}) == 2
    assert sorted(cal + held) == indexes


def test_a_high_fraction_still_leaves_an_animal_on_each_side_of_a_group_of_two():
    identities = _animals({"A": 2}, videos=2)

    cal, held = bv.split_cases(identities, [0, 1, 2, 3], fraction=0.9, seed=5)

    assert len(cal) == 2 and len(held) == 2


def test_videos_without_a_subject_are_animals_of_their_own():
    identities = pd.DataFrame({"group": ["A"] * 4, "subject": [None] * 4})

    cal, held = bv.split_cases(identities, [0, 1, 2, 3], fraction=0.5, seed=2)

    assert len(cal) == 2 and len(held) == 2


@pytest.mark.parametrize("fraction", [0.0, 1.0, -1, 2])
def test_split_rejects_a_fraction_outside_zero_one(fraction):
    with pytest.raises(bv.ValidationInputError, match="between 0 and 1"):
        bv.split_cases(_animals({"A": 4}, videos=1), [0, 1, 2, 3], fraction=fraction, seed=1)


def test_grid_candidates_is_the_cartesian_product_of_the_groups_own_axes():
    grid: dict[str, list[float | int]] = {
        "visit_min_cover": [0.2, 0.3],
        "visit_enter_frames": [1, 2, 3],
        "visit_exit_frames": [],
    }

    candidates = bv.grid_candidates(grid, bv.PARAM_GROUPS["visits"])

    assert len(candidates) == 6
    assert {"visit_min_cover": 0.2, "visit_enter_frames": 3} in candidates
    assert bv.grid_candidates({}, bv.PARAM_GROUPS["entry"]) == [{}]


def test_the_default_grid_only_names_calibratable_parameters_and_contains_the_defaults():
    from zebtrack.analysis.protocols.barnes.contract import BarnesParams

    defaults = BarnesParams().model_dump()
    calibratable = {p for group in bv.PARAM_GROUPS.values() for p in group}

    assert set(bv.DEFAULT_GRID) == calibratable
    for key, values in bv.DEFAULT_GRID.items():
        assert any(math.isclose(v, defaults[key]) for v in values), key
    sizes = {
        g: len(bv.grid_candidates(bv.DEFAULT_GRID, keys)) for g, keys in bv.PARAM_GROUPS.items()
    }
    assert sizes == {"visits": 36, "entry": 81, "strategy": 81}


def test_relative_loss_is_one_at_the_reference_and_below_one_when_better():
    reference = {"mad_encounter": 4.0, "mad_primary_errors": 1.0}

    assert bv.relative_loss(reference, reference) == pytest.approx(1.0)
    better = bv.relative_loss({"mad_encounter": 2.0, "mad_primary_errors": 0.5}, reference)
    assert better < 1.0
    assert bv.relative_loss({"mad_encounter": 8.0, "mad_primary_errors": 2.0}, reference) > 1.0
    assert bv.relative_loss({}, reference) == math.inf
    # a zero reference does not explode
    assert math.isfinite(bv.relative_loss({"mad_encounter": 1.0}, {"mad_encounter": 0.0}))


def test_group_losses_read_the_metrics_each_group_governs():
    summary = _full_result().summary

    visits = bv.group_losses("visits", summary)
    entry = bv.group_losses("entry", summary)
    strategy = bv.group_losses("strategy", summary)

    assert set(visits) == {"mad_encounter", "encounter_censoring_mismatch", "mad_primary_errors"}
    assert visits["encounter_censoring_mismatch"] == 0.0
    assert set(entry) == {"mad_entry", "entry_censoring_mismatch"}
    assert entry["entry_censoring_mismatch"] == 1.0
    assert strategy == {"strategy_disagreement": pytest.approx(1 - 1 / 2)}
    assert bv.group_losses("visits", {}) == {}


class FakeRunner:
    """A recomputer whose app numbers depend on ``visit_min_cover`` only: 0.4 is the truth."""

    def __init__(self, *, sensitive: bool = True) -> None:
        self.notes: list[str] = []
        self._sensitive = sensitive
        self.calls: list[tuple[int, dict[str, Any]]] = []
        self.truth_enc = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0]

    @property
    def base_params(self) -> dict[str, Any]:
        return {"visit_min_cover": 0.3, "visit_enter_frames": 2, "visit_exit_frames": 3}

    def identity_table(self) -> pd.DataFrame:
        rows = [
            {"group": "A" if i % 2 == 0 else "B", "day": "1" if i < 4 else "2", "subject": str(i)}
            for i in range(8)
        ]
        return app_frame(*rows)

    def run_case(self, index: int, overrides: Any = None) -> dict[str, Any]:
        params = {**self.base_params, **dict(overrides or {})}
        self.calls.append((index, params))
        off = 0.0 if (not self._sensitive or math.isclose(params["visit_min_cover"], 0.4)) else 3.0
        row: dict[str, Any] = {c: None for c in bv.APP_COLUMNS}
        row.update(
            status="ok",
            group="A" if index % 2 == 0 else "B",
            day="1" if index < 4 else "2",
            subject=str(index),
            encounter_latency_s=self.truth_enc[index] + off,
            encounter_censored=False,
            primary_errors=2 + (1 if off else 0),
            t_start_s=1.0,
        )
        return row


def _fake_lab() -> dict[str, pd.DataFrame]:
    runner = FakeRunner()
    rows = [
        {
            "group": "A" if i % 2 == 0 else "B",
            "day": "1" if i < 4 else "2",
            "subject": str(i),
            "encounter_latency_s": runner.truth_enc[i],
            "encounter_censored": False,
            "primary_errors": 2,
        }
        for i in range(8)
    ]
    return {"latencies": lab_frame(*rows)}


def test_calibration_finds_the_threshold_that_matches_the_lab_and_reports_held_out():
    runner = FakeRunner()

    outcome = bv.calibrate(
        runner,
        _fake_lab(),
        bv.MatchSpec(),
        grid={"visit_min_cover": [0.2, 0.3, 0.4, 0.5], "visit_enter_frames": [1, 2, 3]},
        seed=3,
        calibration_fraction=0.5,
    )

    assert outcome.chosen["visit_min_cover"] == pytest.approx(0.4)
    # a parameter the data cannot distinguish stays at its current value (tie -> closest)
    assert outcome.chosen["visit_enter_frames"] == 2
    assert outcome.suggested_block == {"protocol_params": {"barnes": {"visit_min_cover": 0.4}}}
    assert outcome.groups["visits"]["status"] == "searched"
    assert outcome.groups["entry"]["status"] == "skipped"
    assert outcome.groups["strategy"]["status"] == "skipped"
    assert set(outcome.calibration_cases).isdisjoint(outcome.held_out_cases)
    assert len(outcome.calibration_cases) + len(outcome.held_out_cases) == 8
    verdict = outcome.held_out_verdict["visits"]
    assert verdict["improves"] is True and verdict["relative_loss"] < 0.5
    # the held-out defaults really are worse than the calibrated ones
    held_default = outcome.held_out_default["latencies"]["encounter"]["observed"]["mad"]
    held_new = outcome.held_out_calibrated["latencies"]["encounter"]["observed"]["mad"]
    assert held_default == pytest.approx(3.0) and held_new == pytest.approx(0.0)


def test_held_out_videos_are_never_analysed_while_searching():
    runner = FakeRunner()

    outcome = bv.calibrate(
        runner,
        _fake_lab(),
        bv.MatchSpec(),
        grid={"visit_min_cover": [0.3, 0.4]},
        seed=1,
        calibration_fraction=0.5,
    )

    searched = {
        c for c, p in runner.calls if p["visit_min_cover"] == 0.4 and c in outcome.held_out_cases
    }
    # held-out cases are run only in the final evaluation (defaults and chosen), never per candidate
    assert searched <= set(outcome.held_out_cases)
    first_held = min(i for i, (c, _p) in enumerate(runner.calls) if c in outcome.held_out_cases)
    last_cal_only = max(
        i for i, (c, _p) in enumerate(runner.calls) if c in outcome.calibration_cases
    )
    assert first_held > 0 and last_cal_only >= 0
    assert all(c in outcome.calibration_cases for c, _p in runner.calls[:first_held])


def test_without_evidence_calibration_keeps_the_defaults_and_says_it_does_not_improve():
    runner = FakeRunner(sensitive=False)

    outcome = bv.calibrate(
        runner,
        _fake_lab(),
        bv.MatchSpec(),
        grid={"visit_min_cover": [0.2, 0.3, 0.4, 0.5]},
        seed=2,
        calibration_fraction=0.5,
    )

    assert outcome.chosen == {"visit_min_cover": 0.3}
    assert outcome.suggested_block == {"protocol_params": {"barnes": {}}}
    assert outcome.held_out_verdict["visits"]["improves"] is False


def test_calibration_refuses_unknown_parameters_too_few_videos_and_huge_grids():
    runner = FakeRunner()
    with pytest.raises(bv.ValidationInputError, match="cannot be calibrated"):
        bv.calibrate(runner, _fake_lab(), bv.MatchSpec(), grid={"n_holes": [18, 20]})
    with pytest.raises(bv.ValidationInputError, match="shrink the grid"):
        bv.calibrate(
            runner,
            _fake_lab(),
            bv.MatchSpec(),
            grid={"visit_min_cover": [0.2, 0.3, 0.4], "visit_enter_frames": [1, 2, 3]},
            max_candidates=4,
        )
    tiny = {
        "latencies": lab_frame(
            {
                "group": "A",
                "day": "1",
                "subject": "0",
                "encounter_latency_s": 10.0,
                "encounter_censored": False,
            }
        )
    }
    with pytest.raises(bv.ValidationInputError, match="at least 4"):
        bv.calibrate(runner, tiny, bv.MatchSpec(), grid={})


def test_the_calibration_report_prints_the_suggested_block_and_the_verdict(tmp_path):
    outcome = bv.calibrate(
        FakeRunner(),
        _fake_lab(),
        bv.MatchSpec(),
        grid={"visit_min_cover": [0.3, 0.4]},
        seed=3,
        calibration_fraction=0.5,
    )
    result = bv.ValidationResult(summary=outcome.held_out_calibrated, pair_tables={})

    paths = bv.write_outputs(tmp_path, result, title="C", calibration=outcome)

    text = paths["report"].read_text(encoding="utf-8")
    assert "## Calibration" in text and "Held-out evaluation" in text
    assert "visit_min_cover: 0.4" in text
    assert "Nothing was written to the project" in text
    assert "Skipped" in text
    with pd.ExcelFile(paths["workbook"]) as workbook:
        assert "calibration" in workbook.sheet_names


# --- recompute: the real analysis on a scripted rat -------------------------------------------

TABLE = BarnesTable(n_holes=20)
PROJECT = {
    "behavioral_config": {"protocol": "barnes", "protocol_params": {"barnes": {"n_holes": 20}}}
}


def _script() -> RatScript:
    """Centre 1 s, poke +3 (a decoy), poke the target ``toca``, then vanish into it."""
    script = RatScript(TABLE.center).stay(1.0)
    script.poke(TABLE.hole_xy(3), travel_s=1.0, dwell_s=0.6)
    script.poke(TABLE.hole_xy(0), travel_s=1.0, dwell_s=0.6)
    return script.vanish(4.0)


def _write_objects(path: Path, script: RatScript, trajectory: pd.DataFrame) -> None:
    """The ``3c_Objetos`` sidecar the recorder writes: heartbeats, the box and the rat."""
    from zebtrack.io.object_sidecar import (
        HEARTBEAT_CLASS_ID,
        HEARTBEAT_ROLE,
        ObjectSidecarMetadata,
        build_object_table,
    )

    metadata = ObjectSidecarMetadata(
        class_names={0: "arena", 1: "experimenter", 2: "rat", 3: "start_box"},
        class_roles={
            "arena": "arena",
            "experimenter": "context",
            "rat": "subject",
            "start_box": "context",
        },
        clock="pts",
    )
    boxes = {int(r.frame): (r.x1, r.y1, r.x2, r.y2) for r in trajectory.itertuples()}
    rows: list[dict[str, Any]] = []
    for frame in range(round(script.t * FPS) + 1):
        base = {
            "frame": frame,
            "timestamp": frame / FPS,
            "t_event_s": frame / FPS,
            "confidence": 0.9,
            "track_id": None,
            "aquarium_id": None,
        }
        rows.append(
            {
                **base,
                "class_id": HEARTBEAT_CLASS_ID,
                "class_name": None,
                "role": HEARTBEAT_ROLE,
                "x1": None,
                "y1": None,
                "x2": None,
                "y2": None,
            }
        )
        if frame < 10:  # the start box and the experimenter leave at 1 s
            for cid, name in ((3, "start_box"), (1, "experimenter")):
                rows.append(
                    {
                        **base,
                        "class_id": cid,
                        "class_name": name,
                        "role": "context",
                        "x1": 300.0,
                        "y1": 200.0,
                        "x2": 340.0,
                        "y2": 230.0,
                    }
                )
        if frame in boxes:
            x1, y1, x2, y2 = boxes[frame]
            rows.append(
                {
                    **base,
                    "class_id": 2,
                    "class_name": "rat",
                    "role": "subject",
                    "x1": x1,
                    "y1": y1,
                    "x2": x2,
                    "y2": y2,
                    "track_id": 1,
                }
            )
    pq.write_table(build_object_table(rows, metadata), path)


def _write_case(
    root: Path, *, group="A", day="1", subject="1", base="rat1", objects: bool = True
) -> Path:
    folder = root / f"Grupo_{group}" / f"Dia_{day}" / f"Sujeito_{subject}"
    folder.mkdir(parents=True)
    script = _script()
    trajectory = script.frame(with_center_columns=True)
    trajectory.to_parquet(folder / f"3_CoordMovimento_{base}.parquet")
    pd.DataFrame(TABLE.arena(), columns=["x", "y"]).to_parquet(
        folder / f"1_ProcessingArea_{base}.parquet"
    )
    roi_rows = [
        {"roi_name": roi.name, "point_index": i, "x": x, "y": y}
        for roi in TABLE.rois()
        for i, (x, y) in enumerate(list(roi.geometry.exterior.coords)[:-1])
    ]
    pd.DataFrame(roi_rows).to_parquet(folder / f"2_AreasOfInterest_{base}.parquet")
    if objects:
        _write_objects(folder / f"3c_Objetos_{base}.parquet", script, trajectory)
    return folder


def _tree_digest(root: Path) -> dict[str, str]:
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


@pytest.fixture
def results_root(tmp_path):
    root = tmp_path / "results"
    _write_case(root)
    return root


def test_discover_cases_reads_identity_from_the_app_folders_and_skips_multi_aquarium(tmp_path):
    root = tmp_path / "r"
    _write_case(root, group="CBD", day="2", subject="07", base="a")
    other = root / "Grupo_X" / "Dia_1" / "Sujeito_1"
    other.mkdir(parents=True)
    pd.DataFrame({"frame": [0]}).to_parquet(other / "3_CoordMovimento_b_aquarium_2.parquet")

    cases, notes = bv.discover_cases(root)

    assert [(c.base, c.group, c.day, c.subject) for c in cases] == [("a", "cbd", "2", "7")]
    assert cases[0].arena is not None and cases[0].rois is not None
    assert len(notes) == 1 and "multi-aquarium" in notes[0]
    with pytest.raises(bv.ValidationInputError, match="not found"):
        bv.discover_cases(tmp_path / "missing")


def test_recompute_runs_the_real_analysis_and_never_touches_the_results(results_root):
    before = _tree_digest(results_root)
    cases, _ = bv.discover_cases(results_root)

    with bv.Recomputer(cases, project_data=PROJECT) as recomputer:
        row = recomputer.run_case(0)

    assert _tree_digest(results_root) == before  # no 7_AnalysisWindow, nothing rewritten
    assert row["status"] == "ok"
    assert row["trial_type"] == "training"
    assert row["t_start_s"] == pytest.approx(1.0)
    assert row["primary_errors"] == 1
    assert row["entry_censored"] is False
    assert 0.0 < row["encounter_latency_s"] < row["entry_latency_s"] < 5.0
    assert (row["group"], row["day"], row["subject"]) == ("a", "1", "1")


def test_recompute_overrides_change_the_outcome_through_barnes_params(results_root):
    cases, _ = bv.discover_cases(results_root)

    with bv.Recomputer(cases, project_data=PROJECT) as recomputer:
        default = recomputer.run_case(0)
        blind = recomputer.run_case(0, {"visit_enter_frames": 99})

    assert default["encounter_censored"] is False
    assert blind["encounter_censored"] is True
    assert blind["encounter_latency_s"] == 240.0
    assert blind["primary_errors"] == 0


def test_recompute_rebuilds_the_window_with_the_overridden_entry_thresholds(results_root):
    """entry_absent_s is a window threshold: a 10 s absence requirement outlasts the 4 s vanish."""
    cases, _ = bv.discover_cases(results_root)

    with bv.Recomputer(cases, project_data=PROJECT) as recomputer:
        entered = recomputer.run_case(0, {"entry_absent_s": 3.0})
        never = recomputer.run_case(0, {"entry_absent_s": 10.0})

    assert entered["entry_censored"] is False
    assert never["entry_censored"] is True
    assert never["entry_latency_s"] == 240.0


def test_recompute_without_a_window_has_no_entry_and_starts_at_the_first_detection(results_root):
    cases, _ = bv.discover_cases(results_root)

    with bv.Recomputer(cases, project_data=PROJECT, window_mode="none") as recomputer:
        row = recomputer.run_case(0)

    assert row["status"] == "ok"
    assert row["entry_latency_s"] is None or math.isnan(row["entry_latency_s"])
    assert math.isnan(row["t_start_s"])


def test_recompute_marks_probe_trials_by_regex_or_by_the_project_entry(results_root):
    cases, _ = bv.discover_cases(results_root)
    entry_project = {
        **PROJECT,
        "batches": [
            {
                "videos": [
                    {
                        "experiment_id": "rat1",
                        "path": "C:/v/rat1.mp4",
                        "protocol_inputs": {"barnes": {"trial_type": "probe"}},
                    }
                ]
            }
        ],
    }

    with bv.Recomputer(cases, project_data=PROJECT, probe_regex=r"Dia_1") as by_regex:
        regex_row = by_regex.run_case(0)
        regex_identity = by_regex.identity_table()
    with bv.Recomputer(cases, project_data=entry_project) as by_entry:
        entry_row = by_entry.run_case(0)
        entry_identity = by_entry.identity_table()

    assert regex_row["trial_type"] == "probe" and entry_row["trial_type"] == "probe"
    assert regex_row["entry_censored"] is None  # probe: no escape box
    assert entry_identity.loc[0, "video_path"] == "C:/v/rat1.mp4"
    # no project entry: no video path to offer (the match falls back to the experiment id)
    assert regex_identity.loc[0, "video_path"] is None
    assert regex_identity.loc[0, "experiment_id"] == "rat1"


def test_recompute_rejects_a_case_without_zones_or_an_unknown_window_mode(tmp_path, results_root):
    cases, _ = bv.discover_cases(results_root)
    with pytest.raises(bv.ValidationInputError, match="unknown window mode"):
        bv.Recomputer(cases, window_mode="weird")

    root = tmp_path / "nozones"
    folder = root / "Grupo_A" / "Dia_1" / "Sujeito_1"
    folder.mkdir(parents=True)
    _script().frame().to_parquet(folder / "3_CoordMovimento_x.parquet")
    bare, _ = bv.discover_cases(root)
    with bv.Recomputer(bare, project_data=PROJECT) as recomputer:
        with pytest.raises(bv.ValidationInputError, match="no zones"):
            recomputer.run_case(0)


def test_preset_kwargs_follow_the_effective_params():
    from zebtrack.analysis.protocols.barnes.contract import BarnesParams
    from zebtrack.core.conditions.presets import barnes_maze_preset_v2

    params = BarnesParams(entry_absent_s=4.5, entry_hold_s=0.8, max_trial_s=200.0).model_dump()

    kwargs = bv.preset_kwargs(params, k_frames=7)

    assert kwargs == {
        "k_frames": 7,
        "max_s": 200.0,
        "entry_min_cover": 0.5,
        "entry_max_visible_fraction": 0.35,
        "entry_hold_s": 0.8,
        "entry_absent_s": 4.5,
        "entry_min_reference_frames": 10,
    }
    assert barnes_maze_preset_v2(**kwargs) is not None


# --- the command line -------------------------------------------------------------------------


def _write_lab_files(tmp_path: Path, *, subject: str = "1") -> Path:
    (tmp_path / "lat.csv").write_text(
        f"Grupo,Dia,Animal,Inicio,Enc,Ent,Err\nA,1,{subject},1.0,2.0,3.2,1\nA,1,99,1.0,5.0,240,0\n",
        encoding="utf-8",
    )
    mapping = tmp_path / "mapping.yaml"
    mapping.write_text(
        yaml.safe_dump(
            {
                "sheets": {
                    "latencies": {
                        "file": "lat.csv",
                        "columns": {
                            "group": "Grupo",
                            "day": "Dia",
                            "subject": "Animal",
                            "start_time_s": "Inicio",
                            "encounter_latency_s": "Enc",
                            "entry_latency_s": "Ent",
                            "primary_errors": "Err",
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return mapping


def test_cli_validate_compares_a_unified_report_with_the_lab_sheet(tmp_path, capsys):
    mapping = _write_lab_files(tmp_path)
    unified = pd.DataFrame(
        {
            "group": ["A"],
            "day": ["1"],
            "subject": ["1"],
            "experiment_id": ["r1"],
            "barnes_status": ["ok"],
            "window_start_s": [1.2],
            "barnes_encounter_latency_s": [2.1],
            "barnes_encounter_censored": [False],
            "barnes_entry_latency_s": [3.0],
            "barnes_entry_censored": [False],
            "barnes_primary_errors": [1],
        }
    )
    unified.to_parquet(tmp_path / "unified_summary_1.parquet")

    code = bv.run(
        [
            "validate",
            "--mapping",
            str(mapping),
            "--unified",
            str(tmp_path / "unified_summary_1.parquet"),
            "--out",
            str(tmp_path / "out"),
        ]
    )

    assert code == 0
    out = capsys.readouterr().out
    assert "report:" in out and "workbook:" in out
    text = (tmp_path / "out" / "report.md").read_text(encoding="utf-8")
    assert "matched 1" in text
    assert "Lab rows with no app counterpart (1)" in text  # subject 99


def test_cli_recompute_validates_against_the_lab_sheet_with_a_real_analysis(
    tmp_path, results_root, capsys
):
    mapping = _write_lab_files(tmp_path)
    project = tmp_path / "project_config.json"
    project.write_text(json.dumps(PROJECT), encoding="utf-8")

    code = bv.run(
        [
            "recompute",
            "--mapping",
            str(mapping),
            "--results-root",
            str(results_root),
            "--project",
            str(project),
            "--set",
            "visit_exit_frames=4",
            "--out",
            str(tmp_path / "out"),
        ]
    )

    assert code == 0
    summary = json.loads((tmp_path / "out" / "summary.json").read_text(encoding="utf-8"))
    latencies = summary["summary"]["latencies"]
    assert latencies["matching"]["matched"] == 1
    assert latencies["entry"]["counts"]["both_observed"] == 1
    with pd.ExcelFile(tmp_path / "out" / "comparison.xlsx") as workbook:
        assert "app_results" in workbook.sheet_names


def test_cli_reports_input_errors_with_exit_code_two(tmp_path, capsys):
    code = bv.run(
        [
            "validate",
            "--mapping",
            str(tmp_path / "nope.yaml"),
            "--unified",
            "x",
            "--out",
            str(tmp_path / "o"),
        ]
    )

    assert code == 2
    assert "error: cannot read the mapping file" in capsys.readouterr().err


def test_cli_set_values_are_parsed_as_json_then_as_text():
    parsed = bv._parse_overrides(
        [
            "visit_min_cover=0.4",
            "visit_enter_frames=3",
            "visit_max_speed_cm_s=null",
            "default_trial_type=probe",
        ]
    )
    assert parsed == {
        "visit_min_cover": 0.4,
        "visit_enter_frames": 3,
        "visit_max_speed_cm_s": None,
        "default_trial_type": "probe",
    }
    with pytest.raises(bv.ValidationInputError, match="key=value"):
        bv._parse_overrides(["oops"])


def test_cli_set_rejects_a_parameter_that_does_not_exist():
    with pytest.raises(bv.ValidationInputError, match=r"unknown BarnesParams.*visit_min_cvoer"):
        bv._parse_overrides(["visit_min_cvoer=0.4"])


def test_a_user_grid_extends_and_replaces_the_default_axes(tmp_path):
    grid_file = tmp_path / "grid.yaml"
    grid_file.write_text("visit_min_cover: [0.25, 0.35]\nentry_hold_s: 0.7\n", encoding="utf-8")

    grid = bv._load_grid(str(grid_file))

    assert grid["visit_min_cover"] == [0.25, 0.35]
    assert grid["entry_hold_s"] == [0.7]
    assert grid["visit_enter_frames"] == bv.DEFAULT_GRID["visit_enter_frames"]


# --- parity with the individual report's own helpers ------------------------------------------
# ``Recomputer`` mirrors three small steps of ``ReportGenerationCoordinator`` so a recompute sees
# the numbers the report saw. Nothing else keeps the copies honest, so these tests compare them.


def test_the_local_space_matches_the_report_coordinators(results_root):
    from zebtrack.coordinators.report_generation_coordinator import ReportGenerationCoordinator

    coordinator: Any = ReportGenerationCoordinator
    cases, _ = bv.discover_cases(results_root)
    polygon = [list(p) for p in TABLE.arena()]
    off_x, off_y, width, height = coordinator._compute_local_space_geometry(None, polygon, 640, 428)
    raw = pd.read_parquet(cases[0].trajectory)

    mine = bv.Recomputer._to_local(raw, off_x, off_y, width, height)
    theirs = coordinator._normalize_df_to_local_space(None, raw, off_x, off_y, width, height)

    pd.testing.assert_frame_equal(mine, theirs)
    with bv.Recomputer(cases, project_data=PROJECT) as recomputer:
        prepared = recomputer._prepare(0)
    assert prepared["height"] == height
    assert prepared["arena"][0] == (polygon[0][0] - off_x, polygon[0][1] - off_y)


@pytest.mark.parametrize(
    "calibration",
    [
        {"pixel_per_cm_x": 2.5, "pixel_per_cm_y": 2.5},
        {"aquarium_width_cm": 184.0, "aquarium_height_cm": 184.0},
        {"pixel_per_cm_x": 0.5, "aquarium_width_cm": 100.0, "aquarium_height_cm": 50.0},
    ],
)
def test_the_pixel_cm_rule_matches_the_report_coordinators(calibration):
    from zebtrack.coordinators.report_generation_coordinator import ReportGenerationCoordinator

    coordinator: Any = ReportGenerationCoordinator
    project = {**PROJECT, "calibration": calibration}
    px_o = float(calibration.get("pixel_per_cm_x", 1.0))
    py_o = float(calibration.get("pixel_per_cm_y", 1.0))

    with bv.Recomputer([], project_data=project) as recomputer:
        mine = recomputer._pixel_cm(400, 400)
    theirs = coordinator._resolve_pixel_cm(None, {}, calibration, 400, 400, px_o, py_o)

    assert mine == pytest.approx(theirs)


def test_without_a_calibration_the_pixel_cm_falls_back_to_the_table_diameter():
    with bv.Recomputer([], project_data=PROJECT) as recomputer:
        default = recomputer._pixel_cm(368, 368)
    with bv.Recomputer([], project_data=PROJECT, table_diameter_cm=200.0) as recomputer:
        explicit = recomputer._pixel_cm(400, 400)

    assert default == pytest.approx((2.0, 2.0))  # 368 px / the 184 cm default table
    assert explicit == pytest.approx((2.0, 2.0))


# --- edges the first tests left open ----------------------------------------------------------


def test_one_shared_path_component_is_not_a_match():
    lab = lab_frame({"video": "D:/lab/CECT_4.mp4"})  # only the file name agrees
    app = app_frame({"video_path": "C:/proj/Dia_1/CECT_4/CECT_4.mp4"})

    result = bv.match_rows(lab, app, bv.MatchSpec())

    assert result.pairs == [] and result.lab_unmatched == [0]


def test_two_videos_with_the_same_trailing_path_are_ambiguous_not_first_come():
    lab = lab_frame({"video": "CECT_4/CECT_4.mp4"})
    app = app_frame(
        {"video_path": "C:/proj/Dia_1/CECT_4/CECT_4.mp4"},
        {"video_path": "C:/proj/Dia_2/CECT_4/CECT_4.mp4"},
    )

    result = bv.match_rows(lab, app, bv.MatchSpec())

    assert result.pairs == []
    assert result.ambiguous[0]["candidates"] and len(result.ambiguous[0]["candidates"]) == 2


def test_a_strategy_the_app_could_not_produce_is_counted_apart_from_a_disagreement():
    lab = lab_frame(
        {"group": "A", "day": 1, "subject": 1, "strategy": "direct"},
        {"group": "A", "day": 1, "subject": 2, "strategy": "serial"},
    )
    app = app_frame(
        {"group": "A", "day": 1, "subject": 1, "strategy_auto": "direct"},
        {"group": "A", "day": 1, "subject": 2, "strategy_auto": None},
    )
    tables = {"strategy": lab}

    block = bv.evaluate(tables, app, bv.match_all(tables, app, bv.MatchSpec()))
    strategy = block.summary["strategy"]["strategy"]

    assert strategy["counts"] == {"pairs": 2, "lab_missing": 0, "app_missing": 1, "compared": 1}
    assert strategy["kappa"]["n"] == 1


# --- hub review of 41824c54 -------------------------------------------------------------------
# 1. effective defaults  2. visits loss cannot be gamed  3. trial key and strict path match
# 4. time base from the recording's own clock  5. --set validated  6. censoring flag derived
# 7. ceiling-imputed view  + newest unified file, split by animal, empty held-out.


def test_recompute_defaults_are_the_effective_params_not_the_raw_override_block():
    with bv.Recomputer([], project_data=PROJECT) as recomputer:
        params = recomputer.base_params
    with bv.Recomputer([], project_data={}) as recomputer:
        bare = recomputer.base_params

    assert params["n_holes"] == 20  # the project's own override
    assert params["visit_min_cover"] == 0.3 and params["entry_absent_s"] == 3.0  # the defaults
    assert bare["n_holes"] == 18 and bare["visit_enter_frames"] == 2  # never an empty dict


class GamingRunner(FakeRunner):
    """``visit_min_cover = 0.5`` hides the hard encounters by turning them into censored ones."""

    def run_case(self, index: int, overrides: Any = None) -> dict[str, Any]:
        row = super().run_case(index, overrides)
        params = {**self.base_params, **dict(overrides or {})}
        truth = self.truth_enc[index]
        hides = math.isclose(params["visit_min_cover"], 0.5)
        if hides and truth >= 45:
            row.update(encounter_latency_s=240.0, encounter_censored=True)
        else:
            row.update(
                encounter_latency_s=truth + (1.0 if hides else 3.0), encounter_censored=False
            )
        row["primary_errors"] = 2
        return row


def test_a_threshold_that_censors_the_hard_encounters_does_not_win_on_the_observed_mad():
    runner = GamingRunner()

    outcome = bv.calibrate(
        runner,
        _fake_lab(),
        bv.MatchSpec(),
        grid={"visit_min_cover": [0.2, 0.3, 0.5]},
        seed=3,
        # 3 of the 4 animals of each group: whatever the seed, both the hidden (truth >= 45)
        # and the visible encounters are in the calibration subset of each group
        calibration_fraction=0.75,
    )

    info = outcome.groups["visits"]
    ranked = {json.dumps(t["params"]): t["relative_loss"] for t in info["top"]}
    # judged on the observed MAD alone 0.5 would be the best (1 s against 3 s); the censoring
    # mismatch it creates makes it the worst
    assert ranked['{"visit_min_cover": 0.5}'] > 1.0
    assert outcome.chosen["visit_min_cover"] == pytest.approx(0.3)
    assert outcome.suggested_block == {"protocol_params": {"barnes": {}}}


def test_a_candidate_that_leaves_a_metric_undefined_is_rejected_not_rewarded():
    reference = {"mad_encounter": 3.0, "mad_primary_errors": 1.0}

    assert bv.relative_loss({"mad_encounter": 0.5}, reference) == math.inf
    assert bv.relative_loss({}, reference) == math.inf
    # a metric the reference never had is not a reason to reject
    assert math.isfinite(bv.relative_loss({**reference, "mad_total_errors": 1.0}, reference))


def test_trial_is_a_match_key_and_separates_the_trials_of_one_day():
    lab = lab_frame(
        {"group": "A", "day": 1, "subject": 1, "trial": 1},
        {"group": "A", "day": 1, "subject": 1, "trial": 2},
    )
    app = app_frame(
        {"group": "A", "day": 1, "subject": 1, "trial": "2"},
        {"group": "A", "day": 1, "subject": 1, "trial": "1"},
    )

    by_trial = bv.match_rows(lab, app, bv.MatchSpec(keys=("group", "day", "subject", "trial")))
    without = bv.match_rows(lab, app, bv.MatchSpec())

    assert by_trial.pairs == [(0, 1), (1, 0)]
    # without the key the two trials are ambiguous: never paired by row order
    assert without.pairs == [] and len(without.ambiguous) == 2


def test_the_mapping_accepts_a_trial_column_and_a_trial_key(tmp_path):
    (tmp_path / "lat.csv").write_text(
        "Grupo,Dia,Animal,Tentativa,Ent\nA,1,7,2,30\nA,1,7,3,45\n", encoding="utf-8"
    )
    mapping_file = _write_mapping(
        tmp_path,
        "match: {keys: [group, day, subject, trial]}\n"
        "sheets: {latencies: {file: lat.csv, columns: {group: Grupo, day: Dia, subject: Animal,"
        " trial: Tentativa, entry_latency_s: Ent}}}",
    )

    mapping = bv.load_mapping(mapping_file)
    table, _ = bv.read_lab_sheet(mapping.sheets["latencies"])

    assert mapping.match.keys == ("group", "day", "subject", "trial")
    assert table["trial"].tolist() == [2, 3]


def test_trials_come_from_a_column_then_the_name_then_the_order_and_are_reported():
    app = app_frame(
        {"group": "A", "day": "1", "subject": "1", "experiment_id": "r_T1", "trial": "2"},
        {"group": "A", "day": "1", "subject": "2", "experiment_id": "rat_Trial_3"},
        {"group": "A", "day": "2", "subject": "1", "experiment_id": "b"},
        {"group": "A", "day": "2", "subject": "1", "experiment_id": "a"},
        {"group": "A", "day": "3", "subject": "1", "experiment_id": "c"},
    )

    out, notes = bv.derive_trials(app, label="x")

    assert out["trial"].tolist() == ["2", "3", "2", "1", None]
    assert notes == [
        "x trial numbers: 1 from a column, 1 from the experiment id / video path, "
        "2 assigned by order within group/day/subject (a guess at the lab's numbering: "
        "check it), 1 without a trial."
    ]


def test_derive_trials_says_nothing_when_every_trial_is_explicit():
    app = app_frame({"group": "A", "day": "1", "subject": "1", "trial": "1"})

    assert bv.derive_trials(app)[1] == []


def test_a_lab_row_with_a_video_path_never_falls_back_to_the_key():
    lab = lab_frame({"video": "D:/lab/X/R1.mp4", "group": "A", "day": 1, "subject": 1})
    app = app_frame({"group": "A", "day": 1, "subject": 1, "video_path": "C:/p/Dia_1/R7/R7.mp4"})

    strict = bv.match_rows(lab, app, bv.MatchSpec())
    by_key = bv.match_rows(lab, app, bv.MatchSpec(use_video_path=False))

    assert strict.pairs == [] and strict.lab_unmatched == [0]
    assert "video path" in strict.reasons[0]
    assert by_key.pairs == [(0, 0)]
    unmatched = bv.match_summary(lab, app, strict)["lab_unmatched"][0]
    assert "no app video shares two or more path components" in unmatched["reason"]


def test_the_trial_comes_from_a_tentativa_folder(tmp_path):
    root = tmp_path / "r"
    _write_case(root / "Tentativa_2", base="x1")

    cases, _ = bv.discover_cases(root)
    with bv.Recomputer(cases, project_data=PROJECT) as recomputer:
        identity = recomputer.identity_table()

    assert cases[0].trial == "2"
    assert identity.loc[0, "trial"] == "2"
    assert recomputer.notes == []  # explicit: nothing to report


def test_without_a_trial_folder_the_trial_is_the_order_and_the_run_says_so(tmp_path):
    root = tmp_path / "r"
    _write_case(root / "a", base="b1")
    _write_case(root / "b", base="a1")

    cases, _ = bv.discover_cases(root)
    with bv.Recomputer(cases, project_data=PROJECT) as recomputer:
        identity = recomputer.identity_table()

    assert dict(zip(identity["experiment_id"], identity["trial"], strict=True)) == {
        "a1": "1",
        "b1": "2",
    }
    assert any("assigned by order" in note for note in recomputer.notes)


def test_recompute_says_which_clock_dated_each_recording(tmp_path):
    with_objects = tmp_path / "with"
    without = tmp_path / "without"
    _write_case(with_objects, base="r1")
    _write_case(without, base="r2", objects=False)

    notes: list[str] = []
    for root in (with_objects, without):
        cases, _ = bv.discover_cases(root)
        with bv.Recomputer(cases, project_data=PROJECT) as recomputer:
            recomputer.run_case(0)
            notes += recomputer.notes

    assert any(n.startswith("r1: time base from objects_heartbeat (10.00 fps video") for n in notes)
    assert any(
        n.startswith("r2: time base from trajectory_timestamps (10.00 fps video") for n in notes
    )


def test_a_recording_that_cannot_be_dated_is_refused_not_given_the_settings_fps(tmp_path):
    root = tmp_path / "r"
    folder = _write_case(root, base="r1", objects=False)
    _script().frame().iloc[:1].to_parquet(folder / "3_CoordMovimento_r1.parquet")
    cases, _ = bv.discover_cases(root)

    with bv.Recomputer(cases, project_data=PROJECT) as recomputer:
        with pytest.raises(bv.ValidationInputError, match="cannot be dated.*refusing"):
            recomputer.run_case(0)


def test_recompute_refuses_unknown_and_invalid_overrides(results_root):
    cases, _ = bv.discover_cases(results_root)

    with bv.Recomputer(cases, project_data=PROJECT) as recomputer:
        with pytest.raises(bv.ValidationInputError, match="unknown BarnesParams.*visit_min_cvoer"):
            recomputer.run_case(0, {"visit_min_cvoer": 0.4})
        with pytest.raises(bv.ValidationInputError, match="invalid BarnesParams override"):
            recomputer.run_case(0, {"visit_min_cover": 5})
        assert recomputer.run_case(0, {"visit_min_cover": 0.4})["status"] == "ok"


def test_a_missing_censoring_column_is_derived_from_the_ceiling_and_said_so(tmp_path):
    frame = _unified_frame().drop(columns=["barnes_entry_censored", "barnes_encounter_censored"])
    frame["barnes_entry_latency_s"] = [240.0, 100.0]
    path = tmp_path / "unified_summary_20260101_000000_000000.parquet"
    frame.to_parquet(path)

    app, notes = bv.read_unified(path)

    assert app["entry_censored"].tolist() == [True, False]
    assert app["encounter_censored"].tolist() == [False, None]  # no latency, no flag
    assert any(
        "2 entry latencies had no censoring flag; derived as latency >= 240 s" in n for n in notes
    )
    assert any("1 encounter latency had no censoring flag" in n for n in notes)


def test_a_derived_ceiling_flag_keeps_240_out_of_the_observed_statistics(tmp_path):
    frame = _unified_frame().drop(columns=["barnes_entry_censored"])
    frame["barnes_entry_latency_s"] = [240.0, 90.0]
    frame["barnes_status"] = "ok"
    path = tmp_path / "unified_summary_20260101_000000_000000.parquet"
    frame.to_parquet(path)
    app, _ = bv.read_unified(path)
    lab = lab_frame(
        {"group": "A", "day": 1, "subject": 1, "entry_latency_s": 240.0, "entry_censored": True},
        {"group": "A", "day": 1, "subject": 2, "entry_latency_s": 80.0, "entry_censored": False},
    )
    tables = {"latencies": lab}

    result = bv.evaluate(tables, app, bv.match_all(tables, app, bv.MatchSpec()))
    entry = result.summary["latencies"]["entry"]

    assert entry["observed"]["n"] == 1  # the 240 s pair is not an observation
    assert entry["censoring"]["both_censored"] == 1


def test_an_existing_censoring_flag_is_never_overridden_by_the_derivation():
    app = app_frame(
        {"entry_latency_s": 240.0, "entry_censored": False},  # the app says it was observed
        {"entry_latency_s": 240.0},
    )

    out, notes = bv.derive_censoring(app, ceiling_s=240.0, label="u")

    assert out["entry_censored"].tolist() == [False, True]
    assert notes == ["u: 1 entry latency had no censoring flag; derived as latency >= 240 s."]


def test_ceiling_imputed_puts_the_lab_at_the_ceiling_wherever_it_is_flagged_censored():
    lab = pd.Series([100.0, math.nan, 30.0])  # a flagged value, a flagged blank, an observation
    lab_cens = pd.Series([True, True, False])
    app = pd.Series([240.0, 240.0, 31.0])
    app_cens = pd.Series([True, True, False])

    result = bv.latency_comparison(app, app_cens, lab, lab_cens)

    imputed = result["ceiling_imputed"]
    assert imputed["n"] == 3  # the blank censored row is kept, not dropped
    assert imputed["bland_altman"]["bias"] == pytest.approx(1 / 3)  # diffs 0, 0, +1
    assert result["observed"]["n"] == 1


def test_the_ceiling_of_the_lab_sheet_is_used_by_the_imputed_view():
    lab = lab_frame(
        *[
            {"group": "A", "day": 1, "subject": i, "entry_latency_s": v, "entry_censored": c}
            for i, (v, c) in enumerate([(180.0, True), (20.0, False), (30.0, False)], start=1)
        ]
    )
    lab.attrs["censor_at_s"] = 180.0
    app = app_frame(
        *[
            {"group": "A", "day": 1, "subject": i, "entry_latency_s": v, "entry_censored": c}
            for i, (v, c) in enumerate([(180.0, True), (21.0, False), (31.0, False)], start=1)
        ]
    )
    tables = {"latencies": lab}

    result = bv.evaluate(tables, app, bv.match_all(tables, app, bv.MatchSpec()))
    entry = result.summary["latencies"]["entry"]

    assert entry["ceiling_imputed"]["bland_altman"]["bias"] == pytest.approx(2 / 3)


def test_a_folder_gives_the_newest_unified_file_by_run_stamp_and_names_it(tmp_path):
    (tmp_path / "total").mkdir()
    (tmp_path / "selecionados").mkdir()
    old = tmp_path / "total" / "unified_summary_20250101_000000_000000.parquet"
    new = tmp_path / "selecionados" / "unified_partial_summary_20260301_120000_000000.parquet"
    _unified_frame().assign(barnes_status="old").to_parquet(old)
    _unified_frame().assign(barnes_status="new").to_parquet(new)

    app, notes = bv.read_unified(tmp_path)

    assert app["status"].tolist() == ["new", "new"]  # name order alone would pick 'unified_summary'
    assert notes[0] == f"Unified file used: {new}"
    assert any(n.startswith("WARNING: this is a PARTIAL unified report") for n in notes)


def test_without_a_run_stamp_the_modification_time_decides(tmp_path):
    import os

    first = tmp_path / "unified_summary_first.parquet"
    second = tmp_path / "unified_summary_second.parquet"
    _unified_frame().to_parquet(first)
    _unified_frame().to_parquet(second)
    os.utime(first, (1_000_000_000, 1_000_000_000))
    os.utime(second, (2_000_000_000, 2_000_000_000))

    assert bv.newest_unified_file(tmp_path) == second


class SingletonRunner(FakeRunner):
    """Eight animals, each alone in its group: every one is a 'single' of the split."""

    def identity_table(self) -> pd.DataFrame:
        return app_frame(*[{"group": f"G{i}", "day": "1", "subject": "1"} for i in range(8)])


def _lab_for(runner: FakeRunner) -> dict[str, pd.DataFrame]:
    identity = runner.identity_table()
    rows = [
        {
            "group": identity.loc[i, "group"],
            "day": identity.loc[i, "day"],
            "subject": identity.loc[i, "subject"],
            "encounter_latency_s": runner.truth_enc[i],
            "encounter_censored": False,
            "primary_errors": 2,
        }
        for i in range(len(identity))
    ]
    return {"latencies": lab_frame(*rows)}


def test_an_empty_held_out_set_is_reported_as_not_evaluated_not_as_keep_the_defaults(tmp_path):
    runner = SingletonRunner()

    outcome = bv.calibrate(
        runner,
        _lab_for(runner),
        bv.MatchSpec(),
        grid={"visit_min_cover": [0.3, 0.4]},
        seed=1,
        calibration_fraction=0.99,
    )
    result = bv.ValidationResult(summary=outcome.held_out_calibrated, pair_tables={})
    paths = bv.write_outputs(tmp_path, result, title="C", calibration=outcome)
    text = paths["report"].read_text(encoding="utf-8")

    assert outcome.held_out_cases == []
    verdict = outcome.held_out_verdict["visits"]
    assert verdict["evaluated"] is False and verdict["improves"] is None
    assert "WARNING: there are no held-out videos, so NOTHING was evaluated" in text
    assert "not evaluated" in text
    assert "keep the defaults" not in text


def test_the_cli_warns_on_stderr_when_calibration_had_nothing_to_hold_out(
    tmp_path, results_root, capsys, monkeypatch
):
    mapping = _write_lab_files(tmp_path)
    project = tmp_path / "project_config.json"
    project.write_text(json.dumps(PROJECT), encoding="utf-8")
    runner = SingletonRunner()
    outcome = bv.calibrate(
        runner,
        _lab_for(runner),
        bv.MatchSpec(),
        grid={"visit_min_cover": [0.3]},
        seed=1,
        calibration_fraction=0.99,
    )
    monkeypatch.setattr(bv, "calibrate", lambda *a, **k: outcome)

    code = bv.run(
        [
            "calibrate",
            "--mapping",
            str(mapping),
            "--results-root",
            str(results_root),
            "--project",
            str(project),
            "--out",
            str(tmp_path / "out"),
        ]
    )

    assert code == 0
    assert "no held-out videos; nothing was evaluated" in capsys.readouterr().err
