# ADR-012: Migrations — weights registry, settings, projects, wizard templates

**Status:** Accepted · **Date:** 2026-10-30 · **Version:** 8.0.0

## Decision

All migrations are **additive with inert defaults**. Nothing persisted by 7.2 is renamed.

| Store | Change | Absent value means |
|---|---|---|
| `weights_config.json` entry | optional `class_roles: {name: role}` | resolve by aliases (ADR-009) |
| OpenVINO cache dir | `<stem>_<sha8>_openvino_model`; a legacy `<stem>_openvino_model` is accepted only if its recorded sha matches, otherwise re-exported | — |
| `settings.model_selection` | `context_inference_scope` (`arena_crop_margin`), `context_crop_margin_frac` (0.15), `context_min_confidence` (`None` = subject threshold) | today's behaviour (only active with context classes) |
| `settings.recorder` | `persist_object_sidecar` (`True`) | — |
| `project_config.json` | `analysis_window: None`, `model_overrides.class_roles: None`, `model_overrides.class_roles_weight_sha256: None` via `apply_project_migrations` | whole recording; aliases |
| `project_config.json` | `model_selection` written from the wizard at creation (fixes the lost-on-reopen bug); projects created before 8.0 are backfilled from `_wizard_metadata["model_selection"]` on load | global settings |
| wizard templates | `TEMPLATE_SCHEMA_VERSION` 3 → 4; a v3 template with `external_trigger_mode=True` becomes `start=External(arduino, 1)`, `stop=External(arduino, 0)`, shown on the confirmation step | — |
| `project_config.json` 7.2 with `external_trigger_mode=True` | **not** converted automatically; the bool and `ARM_AND_WAIT` keep working; the UI offers "convert to condition" | legacy gate |

Persistence contracts kept verbatim: weight targets `aquarium`/`zebrafish`, the four
`is_default_<m>_<t>` flags, slot keys `"det:zebrafish"` etc., `num_aquariums`,
`animals_per_aquarium`, `aquarium_*` keys, `aquarium_id`, `aquarium_{N}/`. New tokens (`subject`,
`arena`, `context`, `ignored`, condition `kind`s, `3c_Objetos_`, `7_AnalysisWindow_`) are English
and enter `scripts/i18n_allowlist.txt` only if the scanner flags them.

## Consequences

`settings.py` keeps `extra="forbid"`; every new field ships in `config.yaml` with its default.
A frozen 7.2.0 project under `tests/fixtures/legacy/project_7_2_0/` guards "opens without manual
migration".
