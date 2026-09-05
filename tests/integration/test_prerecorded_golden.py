"""Numeric golden for the PRE-RECORDED single-video pipeline.

What this protects
------------------
v6.1.0 is a validation milestone: both pre-recorded flows were driven end to end
by hand, from arena auto-detection to the ``.docx`` and ``.xlsx``. The next round
of work is on the LIVE flows, and the previous attempt at that produced four
consecutive repair PRs (#522, #523, #524, #527) on the pre-recorded side.

The failures were not crashes. #524 changed **7 of 9 analysis parameters** on a
real project while every existing test stayed green, because the existing
end-to-end test asserts that files exist, not that the numbers are the same.
This file asserts the numbers.

Reading a failure
-----------------
A diff here means one of two things, and they need opposite responses:

* You changed analysis behaviour ON PURPOSE. Re-record with
  ``ZEBTRACK_UPDATE_GOLDEN=1`` and let the new numbers show up in the diff,
  where a reviewer can see exactly which metric moved and by how much.
* You did not. Then something leaked — most likely a flow writing into the
  shared ``Settings`` object without restoring it. ``test_flow_isolation.py``
  is the file that names the culprit.

Re-recording is meant to be a deliberate, reviewable act. That is the entire
value of the fixture; a golden that gets refreshed reflexively protects nothing.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import pytest

from tests.helpers.prerecorded_pipeline import (
    EXPERIMENT_ID,
    TRAJECTORY_COLUMNS,
    PipelineOutcome,
    load_pristine_settings,
    normalize_report,
    run_prerecorded_pipeline,
)

GOLDEN_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "golden"
TRAJECTORY_GOLDEN = GOLDEN_DIR / "prerecorded_single_trajectory.csv"
REPORT_GOLDEN = GOLDEN_DIR / "prerecorded_single_report.json"

#: Coordinates are integers in pixels and metrics are derived from them, so the
#: only spread expected across machines is float formatting. Kept tight on
#: purpose: a loose tolerance is how a real regression slips through.
RTOL = 1e-9
ATOL = 1e-9


def _updating() -> bool:
    return os.environ.get("ZEBTRACK_UPDATE_GOLDEN", "") == "1"


@pytest.fixture(scope="module")
def outcome(tmp_path_factory) -> PipelineOutcome:
    """Run the pipeline once for the whole module."""
    workdir = tmp_path_factory.mktemp("prerecorded_golden")
    settings = load_pristine_settings()
    try:
        return run_prerecorded_pipeline(workdir, settings)
    except RuntimeError as exc:  # no codec on this machine
        pytest.skip(f"Cannot build the golden fixture video: {exc}")


@pytest.mark.integration
def test_trajectory_matches_golden(outcome: PipelineOutcome) -> None:
    """The recorded trajectory is byte-for-byte the trajectory we signed off on."""
    produced = outcome.trajectory.reset_index(drop=True)

    if _updating() or not TRAJECTORY_GOLDEN.exists():
        GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
        produced.to_csv(TRAJECTORY_GOLDEN, index=False, lineterminator="\n")
        pytest.skip(f"Golden trajectory (re)recorded at {TRAJECTORY_GOLDEN}")

    expected = pd.read_csv(TRAJECTORY_GOLDEN)
    assert list(produced.columns) == list(expected.columns)
    pd.testing.assert_frame_equal(
        produced,
        expected,
        check_exact=False,
        rtol=RTOL,
        atol=ATOL,
        check_dtype=False,
    )


@pytest.mark.integration
def test_analysis_report_matches_golden(outcome: PipelineOutcome) -> None:
    """Every metric the reporters consume is unchanged.

    This is the assertion #524 needed and did not have: freezing time, sharp
    turns, distance and speed all live in this dict.
    """
    produced = normalize_report(outcome.report)

    if _updating() or not REPORT_GOLDEN.exists():
        GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
        REPORT_GOLDEN.write_text(
            json.dumps(produced, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        pytest.skip(f"Golden report (re)recorded at {REPORT_GOLDEN}")

    expected = json.loads(REPORT_GOLDEN.read_text(encoding="utf-8"))
    assert produced == expected


@pytest.mark.integration
def test_trajectory_keeps_the_immutable_column_contract(outcome: PipelineOutcome) -> None:
    """The worker writes the contract schema, in order.

    ``tests/test_recorder.py`` asserts this against the ``Recorder`` directly.
    Asserting it again here covers the other half: that the pre-recorded WORKER
    still drives the recorder in the mode that produces those columns.
    """
    assert list(outcome.trajectory.columns) == TRAJECTORY_COLUMNS
    assert "mask_wkb" not in outcome.trajectory.columns


#: Settings fields the ad-hoc dialogs overwrite globally AND that this fixture
#: can actually detect a change to. Verified empirically, not assumed — see
#: ``test_golden_detects_a_change_to_each_guarded_threshold``.
GUARDED_THRESHOLDS = [
    ("video_processing", "freezing_velocity_threshold", 6.0),
    ("video_processing", "freezing_min_duration_s", 5.0),
    ("video_processing", "sharp_turn_threshold_deg_s", 300.0),
    ("trajectory_smoothing", "window_length", 15),
    ("trajectory_smoothing", "polyorder", 1),
]


@pytest.mark.integration
@pytest.mark.parametrize(("group", "field", "value"), GUARDED_THRESHOLDS)
def test_golden_detects_a_change_to_each_guarded_threshold(
    tmp_path, outcome: PipelineOutcome, group: str, field: str, value: object
) -> None:
    """Perturbing a guarded threshold must move the report.

    This replaces the assumption a golden usually rests on. "The metric is
    non-zero, therefore the fixture exercises the threshold" is not sound, and
    writing this test is what proved it: ``sharp_turns_count`` sat at a healthy
    7 and stayed at exactly 7 whether the threshold was 10 or 2000. A
    non-degeneracy check would have reported full coverage of a field nothing
    could see. The cause was a production defect —
    ``AnalysisService.run_full_analysis`` did not accept the parameter and
    called ``calculate_sharp_turns(90.0)`` with a literal — fixed in the same
    change that added this test, which is why the field is in the list below
    rather than pinned as a known blind spot.

    Each parameter is a field ``LiveAnalysisDialog.apply()`` writes into the
    shared ``Settings``. A failure here means the golden has gone blind to that
    field — the fixture no longer exercises it — and ``test_flow_isolation.py``
    can no longer prove anything about it either.
    """
    settings = load_pristine_settings()
    setattr(getattr(settings, group), field, value)

    perturbed = run_prerecorded_pipeline(tmp_path / f"{group}_{field}", settings)

    assert normalize_report(perturbed.report) != normalize_report(outcome.report), (
        f"changing {group}.{field} did not change the report: the golden is "
        f"blind to it, so a leak of that field would pass unnoticed"
    )


@pytest.mark.integration
def test_golden_metrics_are_not_degenerate(outcome: PipelineOutcome) -> None:
    """The fixture still produces the metrics the reports are built from.

    Weaker than the sensitivity tests above and kept for a different reason: it
    fails loudly and early if the fixture trajectory degenerates into something
    that produces no behaviour at all.
    """
    general = outcome.report["comportamento_geral"]

    assert general["episodios_congelamento"], "no freezing episodes in the fixture"
    assert general["distancia_total_cm"] > 0
    assert general["estatisticas_velocidade"]["mean"] > 0
    assert outcome.report["analise_roi"]["tempo_gasto_por_roi"], "ROI attribution is empty"


@pytest.mark.integration
def test_pipeline_is_reproducible_within_a_run(tmp_path) -> None:
    """Two runs of the same input agree.

    If this fails, the golden is unusable no matter what it contains — and the
    cause is worth knowing, because the pre-recorded flow being deterministic is
    the property the whole regression net rests on.
    """
    settings = load_pristine_settings()
    try:
        first = run_prerecorded_pipeline(tmp_path / "a", settings)
    except RuntimeError as exc:
        pytest.skip(f"Cannot build the golden fixture video: {exc}")
    second = run_prerecorded_pipeline(tmp_path / "b", settings)

    pd.testing.assert_frame_equal(first.trajectory, second.trajectory)
    assert normalize_report(first.report) == normalize_report(second.report)


@pytest.mark.integration
def test_experiment_id_reaches_the_recorded_filenames(outcome: PipelineOutcome) -> None:
    """The three per-video artefacts are written under the expected names."""
    produced = {p.name for p in outcome.output_dir.iterdir()}
    assert f"3_CoordMovimento_{EXPERIMENT_ID}.parquet" in produced
    assert f"1_ProcessingArea_{EXPERIMENT_ID}.parquet" in produced
    assert f"2_AreasOfInterest_{EXPERIMENT_ID}.parquet" in produced
