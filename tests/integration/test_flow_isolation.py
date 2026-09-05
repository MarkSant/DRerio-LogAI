"""Running a LIVE flow must not change what a PRE-RECORDED flow computes.

The defect class
---------------
The four flows (single video, single live, project batch, project live) share
one ``Settings`` object for the lifetime of the app. The ad-hoc dialogs write
the user's per-run choices straight into it and never restore them. PR #524
measured the consequence on a real project: analysing a single video and then
analysing a project applied the single video's thresholds to the project's
videos — **7 of 9 parameters changed** — altering freezing time, sharp turns,
distance and speed with no warning anywhere.

Nothing in the suite could see it, because every test builds its objects fresh.
The bug only exists when flow A and flow B run in the SAME process, which is
what a person does and what CI never did. These tests do exactly that.

What actually protects the app
------------------------------
Not restraint from the writers — they still write. The guard is on the reader
side: ``build_project_settings_snapshot`` resolves **project > baseline >
default**, where ``baseline`` is a pristine copy captured in ``ContainerContext``
before any dialog can exist (``core/di_registrations.py``). The live object never
enters the answer.

That guard has one fragile seam, and it is silent:

    self.settings_baseline = (
        settings_baseline if settings_baseline is not None else settings_obj
    )

Omit the baseline and the fallback is the polluted object itself — protection
gone, no error, no log. ``test_pipeline_IS_corrupted_without_the_baseline`` is
the negative control for precisely that: it proves the guard is load-bearing
rather than decorative, which is the only reason to trust the tests above it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.helpers.prerecorded_pipeline import (
    load_pristine_settings,
    normalize_report,
    run_prerecorded_pipeline,
)
from zebtrack.core.services.project_settings_snapshot import build_project_settings_snapshot
from zebtrack.ui.dialogs.live_analysis_dialog import LiveAnalysisDialog

#: What a person typed into the live dialog. Every value differs from
#: ``config.yaml`` on purpose — a value that matched would prove nothing.
LIVE_CHOICES: dict[str, Any] = {
    "analysis_interval_var": 4,
    "display_interval_var": 6,
    "sharp_turn_var": 20.0,
    "freeze_thresh_var": 5.0,
    "freeze_dur_var": 3.0,
    "smoothing_window_var": 11,
    "smoothing_polyorder_var": 2,
    "aquarium_method_var": "seg",
    "animal_method_var": "seg",
    "use_openvino_var": True,
    "num_aquariums_var": 1,
    "animals_per_aquarium_var": 1,
    "camera_selection_var": "Camera 0",
    "experiment_id_var": "LIVE_RUN",
    "duration_var": 30.0,
    "record_video_var": True,
    "use_countdown_var": False,
    "aquarium_width_var": 20.0,
    "aquarium_height_var": 15.0,
    "output_folder_var": "",
}

#: The fields the dialog writes into the shared object. Kept here as the
#: behavioural counterpart to the AST allowlist in
#: ``tests/quality/test_shared_settings_mutations.py``: that one notices a new
#: assignment appearing, this one notices what the assignment does.
POLLUTED_FIELDS = [
    ("video_processing", "processing_interval"),
    ("video_processing", "display_interval"),
    ("video_processing", "sharp_turn_threshold_deg_s"),
    ("video_processing", "freezing_velocity_threshold"),
    ("video_processing", "freezing_min_duration_s"),
    ("trajectory_smoothing", "window_length"),
    ("trajectory_smoothing", "polyorder"),
    ("model_selection", "aquarium_method"),
    ("model_selection", "animal_method"),
    ("model_selection", "use_openvino"),
    ("analysis_config", "num_aquariums"),
    ("tracking", "use_single_subject_tracker"),
]


class _Var:
    """Minimal stand-in for a Tk variable."""

    def __init__(self, value: Any) -> None:
        self._value = value

    def get(self) -> Any:
        return self._value


def run_live_dialog_apply(settings: Any) -> dict[str, Any]:
    """Drive the REAL ``LiveAnalysisDialog.apply()`` against ``settings``.

    ``apply`` is where the writes live; ``ok()`` is only the Tk hook that calls
    it after ``validate()``. Building the dialog for real would need a display
    and a camera enumeration, so the instance is created without ``__init__``
    and given the widget state ``apply`` reads.

    This is the use of ``object.__new__`` that ``tests/quality/test_no_hollow_tests.py``
    permits: a real method of the real class is executed, and the assertions are
    about what that execution did to a separate object — not a ``setattr`` round
    trip through the instance.
    """
    dialog = object.__new__(LiveAnalysisDialog)
    for name, value in LIVE_CHOICES.items():
        setattr(dialog, name, _Var(value))
    dialog.settings = settings
    dialog.camera_index_map = {"Camera 0": 0}
    dialog.behavioral_config_widget = None
    dialog._countdown_seconds = 0
    dialog.result = None

    dialog.apply()
    assert dialog.result is not None, "apply() did not build a result"
    return dialog.result


@pytest.fixture
def golden_report(tmp_path: Path) -> dict[str, Any]:
    """The pre-recorded report as produced with untouched settings."""
    try:
        outcome = run_prerecorded_pipeline(tmp_path / "reference", load_pristine_settings())
    except RuntimeError as exc:
        pytest.skip(f"Cannot build the fixture video: {exc}")
    return normalize_report(outcome.report)


@pytest.mark.integration
def test_live_dialog_apply_writes_into_the_shared_settings() -> None:
    """Pin the polluter.

    This is not a complaint — the dialog updating the shared object is how the
    other UI tabs stay consistent within a live session. It is pinned because
    every guard below is built on it being true. If a future refactor makes the
    dialog stop writing, these tests would keep passing while testing nothing,
    and this is the test that would fail instead and say so.
    """
    settings = load_pristine_settings()
    before = {(g, f): getattr(getattr(settings, g), f) for g, f in POLLUTED_FIELDS}

    run_live_dialog_apply(settings)

    changed = {
        (g, f) for g, f in POLLUTED_FIELDS if getattr(getattr(settings, g), f) != before[(g, f)]
    }
    assert changed, (
        "LiveAnalysisDialog.apply() no longer mutates the shared Settings. "
        "If that is deliberate, the guards in this file and the allowlist in "
        "tests/quality/test_shared_settings_mutations.py must be revisited."
    )


@pytest.mark.integration
def test_project_snapshot_ignores_live_dialog_pollution() -> None:
    """The reader-side guard: a project snapshot answers from the baseline."""
    baseline = load_pristine_settings()
    shared = load_pristine_settings()

    run_live_dialog_apply(shared)

    snapshot = build_project_settings_snapshot(shared, {}, baseline=baseline)

    assert snapshot.video_processing.freezing_velocity_threshold == (
        baseline.video_processing.freezing_velocity_threshold
    )
    assert snapshot.video_processing.freezing_min_duration_s == (
        baseline.video_processing.freezing_min_duration_s
    )
    assert snapshot.video_processing.sharp_turn_threshold_deg_s == (
        baseline.video_processing.sharp_turn_threshold_deg_s
    )
    assert (
        snapshot.trajectory_smoothing.window_length == baseline.trajectory_smoothing.window_length
    )
    assert snapshot.trajectory_smoothing.polyorder == baseline.trajectory_smoothing.polyorder


@pytest.mark.integration
def test_prerecorded_numbers_survive_a_live_run(
    tmp_path: Path, golden_report: dict[str, Any]
) -> None:
    """The end-to-end claim: live first, then pre-recorded, same numbers.

    The pipeline is fed the snapshot, which is what production does —
    ``VideoProcessingCoordinator.process_videos`` builds one via
    ``_create_project_settings_snapshot`` for the single-video path and the
    batch path alike.
    """
    baseline = load_pristine_settings()
    shared = load_pristine_settings()

    run_live_dialog_apply(shared)

    snapshot = build_project_settings_snapshot(shared, {}, baseline=baseline)
    after_live = run_prerecorded_pipeline(tmp_path / "after_live", snapshot)

    assert normalize_report(after_live.report) == golden_report, (
        "A live-dialog run changed what the pre-recorded pipeline computes. "
        "This is the PR #524 defect returning."
    )


@pytest.mark.integration
def test_pipeline_IS_corrupted_without_the_baseline(
    tmp_path: Path, golden_report: dict[str, Any]
) -> None:
    """Negative control: drop the baseline and the numbers really do move.

    Without this, the three tests above could all be passing because the
    fixture is insensitive rather than because the guard works. Here the guard
    is deliberately bypassed the way the ``or settings_obj`` fallback bypasses
    it — and the report must differ. If this test ever starts passing by
    equality, the golden has gone blind and the rest of the file is worthless.
    """
    shared = load_pristine_settings()
    run_live_dialog_apply(shared)

    unguarded = build_project_settings_snapshot(shared, {}, baseline=None)
    corrupted = run_prerecorded_pipeline(tmp_path / "unguarded", unguarded)

    assert normalize_report(corrupted.report) != golden_report, (
        "Bypassing the baseline no longer changes the result — the fixture "
        "trajectory has stopped exercising the leaked thresholds, so these "
        "tests can no longer detect the defect they exist for."
    )

    general = normalize_report(corrupted.report)["comportamento_geral"]
    reference = golden_report["comportamento_geral"]
    assert (
        general["distancia_total_cm"] != reference["distancia_total_cm"]
        or general["curvas_acentuadas"]["sharp_turns_count"]
        != reference["curvas_acentuadas"]["sharp_turns_count"]
    ), "neither distance nor sharp turns moved; the control is too weak to be meaningful"


@pytest.mark.integration
def test_snapshot_never_mutates_the_object_it_reads() -> None:
    """Building a snapshot must not write back into the shared settings."""
    baseline = load_pristine_settings()
    shared = load_pristine_settings()
    run_live_dialog_apply(shared)

    before = {(g, f): getattr(getattr(shared, g), f) for g, f in POLLUTED_FIELDS}
    build_project_settings_snapshot(shared, {"analysis_parameters": {}}, baseline=baseline)
    after = {(g, f): getattr(getattr(shared, g), f) for g, f in POLLUTED_FIELDS}

    assert before == after
