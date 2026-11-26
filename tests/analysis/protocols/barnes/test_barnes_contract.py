"""``analysis/protocols/barnes/contract.py`` — the Barnes names, params and schemas (#633)."""

from __future__ import annotations

import math

import pytest

from zebtrack.analysis.protocols.barnes import contract as c
from zebtrack.core.conditions.presets import BARNES_BURROW_ROI

# --- tokens ------------------------------------------------------------------


def test_persisted_tokens_are_frozen():
    assert c.TARGET_ROI == BARNES_BURROW_ROI == "toca"
    assert c.QUADRANT_ROI == "quadrante_alvo"
    assert c.OPPOSITE_HOLE_ROI == "buraco_oposto"
    assert c.HOLE_ROI_PREFIX == "buraco_"
    assert c.LAYOUT_METADATA_KEY == "barnes_layout"
    assert c.LAYOUT_SCHEMA_VERSION == 1
    assert c.METRICS_VERSION == 1
    assert c.STOP_REASON_BURROW_ENTRY == "burrow_entry"
    assert c.ASSISTANT_ID == "barnes_layout"
    assert c.EXCEL_VISITS_SHEET == "barnes_visits"
    assert [t.value for t in c.TrialType] == ["training", "probe"]
    assert [s.value for s in c.SearchStrategy] == ["direct", "serial", "random"]
    assert [s.value for s in c.StrategySource] == ["auto", "manual"]
    assert [s.value for s in c.StartSource] == ["window", "recording"]
    assert [s.value for s in c.EntrySource] == [
        "window",
        "censored",
        "unavailable",
        "not_applicable",
    ]


# --- offsets and names -------------------------------------------------------


@pytest.mark.parametrize("n_holes", [3, 4, 5, 18, 19, 20, 21])
def test_infer_n_holes_reads_a_full_layout(n_holes):
    assert c.infer_n_holes(c.expected_roi_names(n_holes)) == n_holes


@pytest.mark.parametrize(
    ("names", "expected"),
    [
        # 2k + 2 with the opposite hole, 2k + 1 without it; k = largest |offset|.
        (["buraco_-08", "buraco_oposto"], 18),
        (["buraco_+08", "buraco_-03"], 17),
        (["toca", "buraco_+09", "buraco_oposto", "quadrante_alvo"], 20),
        # Other names never count, and order or repetition do not matter.
        (["start_box", "buraco_+02", "buraco_+02", "Buraco_+09", "buraco_+9"], 5),
        # No buraco_±NN name: no table described.
        (["toca", "quadrante_alvo"], None),
        (["toca", "buraco_oposto"], None),
        ([], None),
        # buraco_+00 is not a hole name.
        (["buraco_+00", "buraco_oposto"], None),
        # Beyond the n_holes range (3..99).
        (["buraco_+49", "buraco_oposto"], None),
        (["buraco_+49"], 99),
        (["buraco_+01"], 3),
    ],
)
def test_infer_n_holes_from_partial_names(names, expected):
    assert c.infer_n_holes(names) == expected


def test_probe_score_of_the_opposite_hole_is_ten_on_eighteen_holes():
    assert c.probe_score(c.max_offset(18), c.BarnesParams().probe_score_cap) == 10


def test_max_offset():
    assert c.max_offset(20) == 10
    assert c.max_offset(5) == 2
    assert c.max_offset(3) == 1
    with pytest.raises(ValueError):
        c.max_offset(2)


@pytest.mark.parametrize(
    ("abs_index", "expected"),
    [(5, 0), (6, 1), (14, 9), (15, 10), (16, -9), (4, -1), (0, -5), (19, -6), (10, 5)],
)
def test_circular_offset_twenty_holes(abs_index, expected):
    assert c.circular_offset(abs_index, 5, 20) == expected


@pytest.mark.parametrize(("abs_index", "expected"), [(0, 0), (1, 1), (2, 2), (3, -2), (4, -1)])
def test_circular_offset_odd_count_has_no_opposite(abs_index, expected):
    assert c.circular_offset(abs_index, 0, 5) == expected


@pytest.mark.parametrize(
    ("offset", "name"),
    [
        (0, "toca"),
        (1, "buraco_+01"),
        (9, "buraco_+09"),
        (-1, "buraco_-01"),
        (-9, "buraco_-09"),
        (10, "buraco_oposto"),
    ],
)
def test_hole_roi_name_twenty_holes(offset, name):
    assert c.hole_roi_name(offset, 20) == name


def test_hole_roi_name_odd_count_names_the_farthest_holes():
    assert c.hole_roi_name(2, 5) == "buraco_+02"
    assert c.hole_roi_name(-2, 5) == "buraco_-02"


@pytest.mark.parametrize(("offset", "n_holes"), [(11, 20), (-11, 20), (-10, 20), (3, 5)])
def test_hole_roi_name_refuses_impossible_offsets(offset, n_holes):
    with pytest.raises(ValueError):
        c.hole_roi_name(offset, n_holes)


def test_expected_roi_names_twenty_holes():
    names = c.expected_roi_names(20)

    assert names == (
        "quadrante_alvo",
        "toca",
        *(f"buraco_+{k:02d}" for k in range(1, 10)),
        *(f"buraco_-{k:02d}" for k in range(1, 10)),
        "buraco_oposto",
    )
    assert len(names) == 21
    assert len(set(names)) == 21


def test_expected_roi_names_odd_count():
    assert c.expected_roi_names(5) == (
        "quadrante_alvo",
        "toca",
        "buraco_+01",
        "buraco_+02",
        "buraco_-01",
        "buraco_-02",
    )


@pytest.mark.parametrize("n_holes", [3, 4, 5, 18, 20, 21])
def test_every_expected_name_parses_back(n_holes):
    offsets: list[int] = []
    for name in c.expected_roi_names(n_holes):
        parsed = c.parse_barnes_roi_name(name, n_holes)
        assert parsed is not None, name
        if name == "quadrante_alvo":
            assert parsed == c.BarnesRoiName(c.BarnesRoiKind.QUADRANT, None)
            continue
        assert parsed.kind is c.BarnesRoiKind.HOLE
        assert parsed.offset is not None
        assert c.hole_roi_name(parsed.offset, n_holes) == name
        offsets.append(parsed.offset)
    assert sorted(offsets) == sorted(c.circular_offset(i, 0, n_holes) for i in range(n_holes))


def test_the_target_is_recognised():
    assert c.parse_barnes_roi_name("toca", 20) == c.BarnesRoiName(c.BarnesRoiKind.HOLE, 0)
    assert c.parse_barnes_roi_name("buraco_+01", 20) == c.BarnesRoiName(c.BarnesRoiKind.HOLE, 1)


@pytest.mark.parametrize(
    "name",
    [
        "Toca",
        "toca ",
        "buraco_1",
        "buraco_+1",
        "buraco_+00",
        "buraco_-00",
        "buraco_+10",
        "buraco_-10",
        "buraco_+11",
        "buraco_01",
        "Esquerda",
        "",
    ],
)
def test_names_outside_the_contract_are_not_barnes_rois(name):
    assert c.parse_barnes_roi_name(name, 20) is None


def test_the_opposite_name_does_not_exist_with_an_odd_count():
    assert c.parse_barnes_roi_name("buraco_oposto", 5) is None
    assert c.parse_barnes_roi_name("buraco_oposto", 20) == c.BarnesRoiName(c.BarnesRoiKind.HOLE, 10)


@pytest.mark.parametrize(
    ("offset", "cap", "score"),
    [(0, 10, 1), (1, 10, 2), (-1, 10, 2), (8, 10, 9), (9, 10, 10), (10, 10, 10), (10, 11, 11)],
)
def test_probe_score(offset, cap, score):
    assert c.probe_score(offset, cap) == score


def test_probe_score_refuses_a_zero_cap():
    with pytest.raises(ValueError):
        c.probe_score(1, 0)


# --- params ------------------------------------------------------------------


def test_params_defaults_are_the_protocol_values():
    params = c.BarnesParams()

    # The lab's current table (2024 videos); the 2020 photos show 20.
    assert params.n_holes == 18
    assert params.table_diameter_cm == 184.0
    assert params.quadrant_half_holes == 2
    assert params.hole_roi_dilation == 1.25
    assert params.center_radius_ratio == 0.5
    assert params.max_trial_s == 240.0
    assert params.default_trial_type is c.TrialType.TRAINING
    assert params.probe_score_cap == 10
    assert params.visit_min_cover == 0.3
    assert params.visit_enter_frames == 2
    assert params.visit_exit_frames == 3
    assert params.visit_max_speed_cm_s is None
    assert params.entry_min_cover == 0.5
    assert params.entry_max_visible_fraction == 0.35
    assert params.entry_hold_s == 0.5
    assert params.entry_absent_s == 3.0
    assert params.entry_min_reference_frames == 10
    assert params.strategy_direct_max_errors == 3
    assert params.strategy_serial_min_adjacent_fraction == pytest.approx(2 / 3)
    assert params.strategy_serial_max_center_crossings == 1
    assert params.strategy_adjacent_max_step == 2


def test_parse_params_without_input_gives_the_defaults():
    assert c.parse_barnes_params(None) == (c.BarnesParams(), ())
    assert c.parse_barnes_params({}) == (c.BarnesParams(), ())


def test_parse_params_keeps_valid_values():
    params, warnings = c.parse_barnes_params({"n_holes": 18, "max_trial_s": 180})

    assert (params.n_holes, params.max_trial_s) == (18, 180.0)
    assert warnings == ()


def test_parse_params_ignores_unknown_keys():
    params, warnings = c.parse_barnes_params({"future_knob": 1})

    assert params == c.BarnesParams()
    assert warnings == ()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("n_holes", 2),
        ("table_diameter_cm", 0),
        ("visit_min_cover", 1.5),
        ("entry_max_visible_fraction", 1.0),
        ("default_trial_type", "exam"),
        ("max_trial_s", "long"),
    ],
)
def test_a_bad_field_falls_back_to_its_default_with_a_warning(field, value):
    params, warnings = c.parse_barnes_params({field: value, "probe_score_cap": 9})

    assert getattr(params, field) == getattr(c.BarnesParams(), field)
    assert params.probe_score_cap == 9  # the valid neighbour survives
    assert len(warnings) == 1
    assert field in warnings[0]


def test_a_quadrant_that_does_not_fit_drops_the_offending_fields():
    params, warnings = c.parse_barnes_params({"n_holes": 4, "quadrant_half_holes": 2})

    assert params == c.BarnesParams()
    assert len(warnings) == 2


def test_a_quadrant_wider_than_the_table_alone_is_dropped():
    params, warnings = c.parse_barnes_params({"quadrant_half_holes": 10})

    assert params.quadrant_half_holes == 2
    assert len(warnings) == 1


def test_params_are_immutable():
    with pytest.raises(Exception):  # noqa: B017 - pydantic's frozen error type
        c.BarnesParams().n_holes = 18  # type: ignore[misc]


# --- per-video inputs --------------------------------------------------------


def test_video_inputs_default_to_undeclared():
    assert c.parse_barnes_video_inputs(None) == (c.BarnesVideoInputs(), ())
    inputs, _ = c.parse_barnes_video_inputs({})
    assert inputs.trial_type is None and inputs.strategy_override is None


def test_video_inputs_are_parsed():
    inputs, warnings = c.parse_barnes_video_inputs(
        {"trial_type": "probe", "strategy_override": "serial", "note": "x"}
    )

    assert inputs.trial_type is c.TrialType.PROBE
    assert inputs.strategy_override is c.SearchStrategy.SERIAL
    assert warnings == ()


def test_a_bad_video_input_is_dropped_with_a_warning_and_the_other_kept():
    inputs, warnings = c.parse_barnes_video_inputs(
        {"trial_type": "exam", "strategy_override": "direct"}
    )

    assert inputs.trial_type is None
    assert inputs.strategy_override is c.SearchStrategy.DIRECT
    assert len(warnings) == 1
    assert "trial_type" in warnings[0]


def test_a_none_video_input_is_simply_undeclared():
    inputs, warnings = c.parse_barnes_video_inputs({"trial_type": None})

    assert inputs.trial_type is None
    assert warnings == ()


# --- layout ------------------------------------------------------------------


def _ring_layout(n_holes: int = 20, target: int = 3) -> c.BarnesLayout:
    ring = c.BarnesEllipse(center_px=(320.0, 214.0), semi_axes_px=(200.0, 180.0), angle_deg=0.0)
    table = c.BarnesEllipse(center_px=(320.0, 214.0), semi_axes_px=(238.0, 212.0), angle_deg=0.0)
    holes = []
    for index in range(n_holes):
        angle = 2 * math.pi * index / n_holes
        holes.append(
            c.BarnesHole(
                offset=c.circular_offset(index, target, n_holes),
                abs_index=index,
                center_px=(320.0 + 200.0 * math.cos(angle), 214.0 + 180.0 * math.sin(angle)),
                radius_px=14.0,
                snapped=index % 2 == 0,
                residual_px=1.5 if index % 2 == 0 else None,
            )
        )
    return c.BarnesLayout(
        n_holes=n_holes,
        target_abs_index=target,
        table=table,
        ring=ring,
        holes=tuple(holes),
        source="snapped",
    )


def test_layout_round_trips_through_metadata():
    layout = _ring_layout()

    restored = c.BarnesLayout.from_metadata(layout.to_metadata())

    assert restored == layout
    assert layout.to_metadata()["schema"] == 1
    assert layout.to_metadata()["holes"][0] == {
        "offset": -3,
        "abs_index": 0,
        "center_px": [520.0, 214.0],
        "radius_px": 14.0,
        "snapped": True,
        "residual_px": 1.5,
    }


def test_layout_accessors():
    layout = _ring_layout(target=3)

    assert layout.target.abs_index == 3
    assert layout.target.offset == 0
    assert layout.holes[13].offset == 10
    assert layout.holes[14].offset == -9


@pytest.mark.parametrize("raw", [None, [], "layout", {}, {"n_holes": 20}])
def test_a_missing_or_broken_cache_is_ignored(raw):
    assert c.BarnesLayout.from_metadata(raw) is None


def test_a_cache_with_a_bad_hole_is_ignored():
    raw = _ring_layout().to_metadata()
    raw["holes"][2]["radius_px"] = -1.0

    assert c.BarnesLayout.from_metadata(raw) is None


def test_a_cache_with_a_bad_ellipse_is_ignored():
    raw = _ring_layout().to_metadata()
    raw["ring"]["semi_axes_px"] = [0.0, 10.0]

    assert c.BarnesLayout.from_metadata(raw) is None


def test_a_cache_from_a_future_schema_is_ignored():
    raw = _ring_layout().to_metadata()
    raw["schema"] = 2

    assert c.BarnesLayout.from_metadata(raw) is None


def test_layout_validation():
    layout = _ring_layout()

    with pytest.raises(ValueError, match="holes for"):
        c.BarnesLayout(20, 3, layout.table, layout.ring, layout.holes[:19])
    with pytest.raises(ValueError, match="target_abs_index"):
        c.BarnesLayout(20, 20, layout.table, layout.ring, layout.holes)
    with pytest.raises(ValueError, match="sorted"):
        c.BarnesLayout(20, 3, layout.table, layout.ring, tuple(reversed(layout.holes)))
    with pytest.raises(ValueError, match="offset"):
        c.BarnesLayout(20, 4, layout.table, layout.ring, layout.holes)
    with pytest.raises(ValueError, match="source"):
        c.BarnesLayout(20, 3, layout.table, layout.ring, layout.holes, source="guess")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="schema"):
        c.BarnesLayout(20, 3, layout.table, layout.ring, layout.holes, schema=2)


# --- metrics schema ----------------------------------------------------------


def test_metrics_keys_start_with_the_shared_protocol_shape():
    assert c.METRICS_KEYS[:4] == ("status", "protocol", "version", "reason")
    assert len(c.METRICS_KEYS) == len(set(c.METRICS_KEYS)) == 30


def test_visit_fields_and_sheet_columns():
    assert c.VISIT_FIELDS == (
        "order",
        "roi",
        "offset",
        "distance",
        "t_enter_s",
        "t_exit_s",
        "dwell_s",
        "is_target",
        "is_perseverative",
        "before_encounter",
    )
    assert c.EXCEL_VISIT_COLUMNS == ("experiment_id", *c.VISIT_FIELDS)


def test_tidy_columns_for_twenty_holes():
    columns = c.barnes_tidy_columns(20)

    assert columns[0] == "barnes_status"
    assert columns[1] == "barnes_trial_type"
    assert columns[-11:] == tuple(f"barnes_visits_d{d:02d}" for d in range(11))
    assert len(columns) == 23 + 11
    assert all(column.startswith("barnes_") for column in columns)
    assert len(set(columns)) == len(columns)


def test_tidy_columns_scale_with_the_hole_count():
    assert c.barnes_tidy_columns(5)[-3:] == (
        "barnes_visits_d00",
        "barnes_visits_d01",
        "barnes_visits_d02",
    )


def test_every_tidy_column_reads_a_metrics_key():
    top_level = set(c.METRICS_KEYS)
    for column in c.barnes_tidy_columns(20):
        source = c.tidy_column_source(column)
        assert source.split(".")[0] in top_level, column


def test_tidy_column_sources():
    assert c.tidy_column_source("barnes_entry_latency_s") == "entry_latency_s"
    assert c.tidy_column_source("barnes_center_crossings") == ("strategy_features.center_crossings")
    assert c.tidy_column_source("barnes_visits_d07") == "visits_by_distance.7"
    with pytest.raises(KeyError):
        c.tidy_column_source("window_status")
