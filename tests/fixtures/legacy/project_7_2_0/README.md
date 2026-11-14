# Frozen 7.2.0 project

A pre-recorded zebrafish project exactly as DRerio LogAI 7.2.0 wrote it, kept to
guard ADR-013 invariant 4: a 7.2.0 project opens, processes and reports without
manual migration.

- `project_config.json`: 2 days × 2 groups × 2 fish, `_wizard_metadata` schema v3
  (the det/seg choice lives only there), `model_overrides.slot_weights` with the
  `"det:zebrafish"` / `"seg:aquarium"` contract keys, valid `_integrity_hash`.
  No `analysis_window`, no `model_selection`, no `model_overrides.class_roles`.
- `weights_config.json`: the four lateral/top-down specialists, no `class_roles`,
  and an OpenVINO export registered under the 7.2 cache name
  (`<stem>_openvino_model`, no recorded source sha).

Never edit these files by hand and never regenerate them with 8.x code: the
test copies them to a temporary folder because loading migrates and re-saves.
Guarded by `tests/integration/test_legacy_project_7_2_0.py`.
