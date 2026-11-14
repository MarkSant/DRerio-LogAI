# ADR-009: Class roles — any weight, any class set

**Status:** Accepted · **Date:** 2026-10-30 · **Version:** 8.0.0

## Context

The detector assumes two fixed roles, arena and animal, resolved by name lists and falling back
to positions 0/1 (see [AUDIT](AUDIT.md) §1). Roboflow exports classes alphabetically, so a rodent
weight `{0: arena, 1: experimenter, 2: rat, 3: start_box}` silently tracked the experimenter
until `5fa0f8d2` introduced `class_aliases.py`. v8 must accept any YOLOv8/v11 weight and let the
user say what each class *is*.

## Decision

1. **Roles.** `ClassRole` ∈ {`subject`, `arena`, `context`, `ignored`} in
   `core/detection/class_roles.py`. The four tokens are persistence contracts (never translated).
2. **`ClassRoleMap`** (Pydantic v2, frozen, `extra="forbid"`) stores roles **by normalised class
   name**, never by id: `roles_by_name`, `names` (as read from the model), `source`
   (`project` | `weight` | `aliases` | `legacy_positional`), `weight_sha256`. Ids are resolved
   against `model.names` at load time; derived `subject_ids`, `arena_id`, `context_ids`,
   `to_legacy_tuple()`.
3. **One resolver**, `resolve_class_role_map(names, *, project_override, weight_entry, aliases)`,
   precedence:
   1. project override `model_overrides.class_roles` + `class_roles_weight_sha256` — discarded
      with a warning if the sha does not match the effective weight;
   2. `class_roles` on the `weights_config.json` entry (imported from the `.pt` sibling JSON);
   3. aliases (`class_aliases.py`): animal → subject, arena → arena, everything else → ignored.
      **Aliases never produce `context`**, so zebrafish weights gain no cost;
   4. positional (0, 1) only when the model has no names.
4. **Validation.** ≥ 1 subject, ≤ 1 arena. A weight with names, ≥ 3 classes and no resolvable
   subject raises `ClassRolesUnresolvedError` (typed — never branch on message text);
   `DetectorService._validate_model_classes` stops merely logging. A class absent from an
   explicit map is `ignored`.
5. **Detectors.** `== animal_class_id` becomes `in subject_ids` (single and multi). All raw
   detections whose class is subject or context are captured right after `offset_detections`
   (`single_detector.py:397`) and exposed through `pop_class_observations()`, the same contract
   as `pop_track_masks()`. `apply_class_mismatch_fallback` runs only when
   `source ∈ {aliases, legacy_positional}`.
6. **Context and the arena crop.** The polygon filter applies to subjects only. When the map has
   context classes, context boxes are accepted inside the arena rectangle expanded by
   `model_selection.context_crop_margin_frac` (default 0.15). Without context classes the crop is
   byte-for-byte today's.
7. **Worker.** `core/services/worker_model_resolution.resolve_worker_model()` resolves the
   effective weight in the main process (`WeightManager` + project overrides) and ships
   `model_path`, `weight_sha256` and `class_roles` (plain dict, pickle-safe) in `WorkerConfig`.
   The settings-based path in `processing_worker.py` becomes a warned fallback.
8. **OpenVINO NMS** becomes per class when the model has > 2 classes or any context role; legacy
   2-class weights keep the agnostic NMS.
9. **Multiple subject classes** share one `track_id` axis (no per-class report).

## Consequences

- A retrain that inserts a class does not shift roles.
- The legacy path (no explicit map) runs literally the same code as 7.2.
- Risk: if a subject switches class mid-track and the tracker opens a new id, `unique_tracks > 1`
  flips the report to `any_track` semantics — covered by a dedicated warning.
