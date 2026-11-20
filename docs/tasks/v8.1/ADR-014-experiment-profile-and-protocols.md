# ADR-014: Experiment profile (animal model + protocol) and the protocol registry

**Status:** Accepted · **Date:** 2026-11-19 · **Version:** 8.1.0 (in progress) · **Issue:** #633

## Context

Until v8.0 nothing in a project said *what* was being studied. The app assumed
zebrafish-in-an-aquarium everywhere: interface vocabulary ("aquarium", "fish"),
behavioural defaults (50 cm/s speed ceiling, 1.5 cm thigmotaxis), report contents.
v8 made the detector species-neutral through class roles (ADR-009) and added the
analysis window (ADR-011), whose Barnes preset is the first protocol-specific
behaviour; the protocol itself was still only recognisable by a ROI that happened to
be called `toca`.

Issue #633 asks for the Barnes-maze metrics of the lab's protocol (encounter vs
entry latency, primary/total errors, search strategy, probe score). Those metrics
are meaningless for a zebrafish novel-tank test, and the zebrafish metrics are
partly meaningless for a rat on a Barnes table (geotaxis). The app needs to know
both *which animal* (vocabulary, defaults) and *which protocol* (zones, window,
metrics, reports) — two independent axes: a generic open field can hold a fish or
a rat; a Barnes maze always holds a rodent.

## Decision

1. **Two keys in `behavioral_config`**, the dict every analysis entry point already
   receives (#695):
   - `animal_model ∈ {zebrafish, rodent, other}`;
   - `protocol ∈ {generic, barnes}`;
   - `protocol_params = {<protocol>: {...}}`, validated by the protocol's module.

   No key means `zebrafish` + `generic`: a legacy project is untouched.
2. **One reader**: `core/services/experiment_profile.resolve_experiment_profile()`.
   Precedence per key: the run's `behavioral_config` > the project's block >
   default. Bad values degrade with a warning (unknown model → `other`; unknown
   protocol → generic **but** reported as `unknown_protocol`, never passed off as
   generic). A protocol may force the model (`barnes` → `rodent`). Reading the keys
   anywhere else fails `tests/quality/test_single_source_rules.py`.
3. **A protocol is a `ProtocolSpec`** (`analysis/protocols/`): `compute_metrics`,
   tidy columns, suppressed generic report sections, window preset, zone assistant.
   `generic` is the absence of a spec. Specs are registered in
   `analysis/protocols/registry.py::_builtin_specs`, built lazily.
4. **`report["protocol_metrics"]` is always present** (like `analysis_window`):
   exactly `{"status": "none"}` for a generic project; otherwise
   `status ∈ {ok, unavailable, error}` with `protocol`, `version` and `reason`. It is
   written by one hook at the end of `AnalysisService.run_full_analysis`, after every
   generic metric and with the analysers already cut to the window. A protocol's
   failure never costs the report: it becomes status `error` plus a validation
   warning.
5. **Per-video protocol data** lives in `video_entry["protocol_inputs"][<protocol>]`
   (a Barnes trial type, a manual strategy correction), read and written only through
   `protocol_inputs_of_entry` / `set_protocol_input`. Every single-arena analysis
   entry point passes it as `run_full_analysis(protocol_inputs=...)`; a live session
   reads it from its registered video entry, looked up by path.

## Consequences

- The report dict of a generic project gains one key, declared in
  `EXPECTED_V8_CHANGES` of the v7.2 golden test and in the re-recorded v8 golden.
  Tidy columns, xlsx, docx and parquet outputs of a generic project are unchanged.
- New report keys, tidy columns and sheet names are English (ADR-012). Barnes ROI
  names (`toca`, `quadrante_alvo`, `buraco_±NN`, `buraco_oposto`) stay Portuguese:
  they are lab-facing data, and `toca` was already the preset's contract.
- Multi-aquarium analysis paths do not pass `protocol_inputs`; they pass `aquarium_id`,
  and the hook reports any non-generic protocol as `unavailable` / `multi_aquarium`
  without calling it: no current protocol supports more than one arena per video.
- The whole non-generic branch of the hook (context construction included) is guarded:
  a failure becomes status `error` plus a warning, never an exception in the report.
- A live session reads its per-video inputs from its registered video entry (by path);
  an unregistered session uses the protocol's project-level defaults.
- The interface vocabulary per animal model is a separate front
  (`ui/terminology.py`); persisted `aquarium_*` keys never change.

## Alternatives rejected

- **Protocol only, vocabulary derived from it.** A generic open field could not tell a
  fish from a rat.
- **Templates only, no new keys.** Ad-hoc single-video and live sessions have no
  template, and nothing at analysis time could tell which metrics to compute.
- **Per-video data in `video_entry["metadata"]`.** The summary path copies only six
  metadata keys, and every metadata key becomes a tidy column in front of the
  metrics; it would have needed the same plumbing with a worse shape.
- **A second implementation of the burrow-entry rule in the metrics.** ADR-011 keeps
  one evaluator; the entry instant comes from the window's STOP (`burrow_entry`).

Contract details for the Barnes fronts:
[`barnes/CONTRACTS.md`](barnes/CONTRACTS.md).
