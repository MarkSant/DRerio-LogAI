"""Synthetic Barnes trials pushed through the REAL ``ReporterContext`` (#633, stage 2).

A plain module (not ``conftest``), imported by its full ``tests.`` path. It reuses the
metrics front's table and scripted rat (``barnes_builders``) and adds the one thing the
reporters need on top: a ``ReporterContext`` whose ``report["protocol_metrics"]`` comes
out of ``AnalysisService.run_full_analysis`` itself, so every reporter test reads the
metrics the product would have written.

The lab's table has 18 holes (CONTRACTS section 3.2), so the default table here has 18.
"""

from __future__ import annotations

from typing import Any

from tests.analysis.protocols.barnes.barnes_builders import (
    V2_SPEC,
    BarnesTable,
    RatScript,
    window,
)

from zebtrack.analysis.reporters import ReporterContext
from zebtrack.settings import load_settings

N_HOLES = 18
TABLE = BarnesTable(n_holes=N_HOLES)

#: What a Barnes project's ``behavioral_config`` carries (CONTRACTS section 1).
BARNES_CONFIG: dict[str, Any] = {
    "animal_model": "rodent",
    "protocol": "barnes",
    "protocol_params": {"barnes": {"n_holes": N_HOLES}},
    "aquarium_perspective": "top_down",
}


def scripted_rat(*offsets: int, dwell_s: float = 0.6) -> RatScript:
    """A rat that leaves the start box (1 s) and pokes ``offsets`` in order."""
    script = RatScript(TABLE.center).stay(1.0)
    for offset in offsets:
        script.poke(TABLE.hole_xy(offset), travel_s=1.0, dwell_s=dwell_s)
    return script


def entry_window(script: RatScript):
    """START at 1 s, STOP (``burrow_entry``) when the script ends."""
    return window(1.0, script.t, reason="burrow_entry", spec=V2_SPEC)


def barnes_context(
    script: RatScript,
    *,
    experiment_id: str = "RAT_01",
    protocol_inputs: dict[str, Any] | None = None,
    behavioral_config: dict[str, Any] | None = None,
    extra_metadata: dict[str, Any] | None = None,
    with_window: bool = True,
) -> ReporterContext:
    """A ``ReporterContext`` for the scripted trial, built through the legacy path."""
    metadata = {"experiment_id": experiment_id, "group_id": "G1", **(extra_metadata or {})}
    return ReporterContext(
        trajectory_df=script.frame(),
        metadata=metadata,
        pixelcm_x=1.0,
        pixelcm_y=1.0,
        video_height_px=428,
        arena_polygon_px=list(TABLE.arena()),
        rois=TABLE.rois(),
        fps=10.0,
        freezing_threshold=1.0,
        freezing_duration=1.0,
        settings_obj=load_settings(),
        behavioral_config=dict(BARNES_CONFIG if behavioral_config is None else behavioral_config),
        window=entry_window(script) if with_window else None,
        protocol_inputs=protocol_inputs,
    )


def tidy_row(
    group: str,
    day: str,
    subject: str,
    *,
    trial_type: str = "training",
    encounter: float | None = 30.0,
    encounter_censored: bool = False,
    entry: float | None = 60.0,
    entry_censored: bool | None = False,
    primary: int = 1,
    total: int = 2,
    strategy: str | None = "serial",
    strategy_source: str = "auto",
    status: str = "ok",
    probe_offset: int | None = None,
    probe_score: int | None = None,
    probe_error_latency: float | None = None,
    probe_attempts: int | None = None,
    quadrant_pct: float | None = 25.0,
) -> dict[str, Any]:
    """One unified-report row: metadata plus the ``barnes_*`` columns the product writes.

    The Barnes values come out of ``barnes_columns`` itself (from a metrics dict shaped as
    CONTRACTS section 7), so a test row can never drift from the real schema.
    """
    from zebtrack.analysis.data_transformer import barnes_columns

    metrics: dict[str, Any] = {"status": status, "protocol": "barnes", "version": 1}
    if status == "ok":
        metrics.update(
            trial_type=trial_type,
            encounter_latency_s=encounter,
            encounter_censored=encounter_censored,
            entry_latency_s=entry,
            entry_censored=entry_censored,
            entry_source="not_applicable" if trial_type == "probe" else "window",
            primary_errors=primary,
            total_errors=total,
            perseverative_errors=0,
            primary_path_length_cm=100.0,
            entry_path_length_cm=120.0,
            target_quadrant_time_s=10.0,
            target_quadrant_time_pct=quadrant_pct,
            visits_by_distance={d: 0 for d in range(10)},
            strategy=strategy,
            strategy_source=None if strategy is None else strategy_source,
            strategy_auto=strategy,
            strategy_features={"center_crossings": 0, "adjacent_transition_fraction": 1.0},
            probe_first_hole_offset=probe_offset,
            probe_first_hole_score=probe_score,
            probe_first_error_latency_s=probe_error_latency,
            probe_attempts_to_target=probe_attempts,
        )
    row: dict[str, Any] = {
        "group_id": group,
        "day": day,
        "subject": subject,
        "experiment_id": f"{group}_{day}_{subject}",
        "total_distance_cm": 500.0,
        "mean_speed_cm_s": 5.0,
    }
    row.update(barnes_columns({"protocol_metrics": metrics}, BARNES_CONFIG))
    return row
