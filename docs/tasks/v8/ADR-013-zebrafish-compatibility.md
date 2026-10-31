# ADR-013: Zebrafish compatibility — invariants and deliberate changes

**Status:** Accepted · **Date:** 2026-10-30 · **Version:** 8.0.0

## Invariants (guarded by tests)

1. A weight with no explicit `class_roles` behaves exactly as in 7.2: same class ids, same crop,
   same `apply_class_mismatch_fallback`, same NMS for 2-class OpenVINO models.
2. A project without `analysis_window` analyses the whole recording.
3. `3_CoordMovimento` schema and column order are unchanged.
4. A 7.2.0 project (frozen fixture) opens, processes and reports without manual migration.
5. Persistence contracts listed in [ADR-012](ADR-012-migrations.md) are untouched.

The pre-recorded golden is frozen as `prerecorded_single_report_v72.json`; a test asserts the
v8 report equals it on every key except an explicit allowlist `EXPECTED_V8_CHANGES`.

## Deliberate changes (bug fixes that move numbers)

| Change | Why | Who notices |
|---|---|---|
| ROI latency: rising edge instead of XOR; explicit t0 | an exit was counted as the first entry; golden had `Esquerda = None` with 1 entry | any ROI latency |
| `duracao_video_s` from timestamps, not rows | wrong whenever `analysis_interval_frames > 1` or tracks ≠ 1 | `video_duration_s` xlsx column |
| fps from the video/ledger instead of the global 30 | VFR and non-30 fps videos had wrong time bases | all time-normalised metrics |
| new `analysis_window`, `latency_censored`, `latency_present_at_start` report keys and `window_*` xlsx columns (always present) | analysis windows | unified report consumers |
| new `3c_Objetos_` file per video | ADR-010 | output folder listings |
| live re-analysis re-timed from the frame ledger | processing clock ≠ capture clock | re-analysed live sessions |

Each row is listed in the CHANGELOG under 8.0.0 "Changed".
