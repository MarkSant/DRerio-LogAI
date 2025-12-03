# Sprint 27 – Project Lifecycle Extraction (Executive Summary)

> Detailed references:
>
> - [Analysis](../analysis/SPRINT_27_ANALYSIS.md)
> - [Recommendation deck](../plans/SPRINT_27_RECOMMENDATION.md)

## Objective

- Reduce `MainViewModel` by ~400 lines by extracting the entire project lifecycle
  surface into `ProjectOrchestrator`.
- Focus on workflows and project-specific model overrides without disrupting
  the live camera/recording paths.

## Scope Delivered (385 lines / 14 methods)

| Group | Theme | Methods | Risk | Notes |
| --- | --- | --- | --- | --- |
| A | Lifecycle orchestration | `close_project`, `create/open_project_workflow`, `start_project_processing_workflow`, `process_pending_project_videos` | Low | Pure delegations to existing adapters and video orchestrator. |
| B | Model override management | `_get_project_data_dict`, `_ensure_project_overrides_record`, `_persist_project_model_settings`, `copy_global_model_settings_to_project`, `save_current_calibration_to_project`, `resolve_project_model_settings`, `are_project_overrides_active`, `has_project_override_settings` | Medium | Heavy interaction with `project_manager.project_data`; keep UI event emission inside the ViewModel. |
| C | Asset lifecycle | `can_remove_project_asset`, `delete_project_asset`, `_register_project_outputs` | Low | Mostly validation and state refresh hooks. |
| D | Supporting glue | `_setup_zones_from_project`, `project_calibration_session` | Medium | Calibration context requires thorough tests for teardown paths. |

## Sequencing & Mitigations

1. **Extract groups A & C first** – minimal state, quick wins.
2. **Follow with group D** – context manager and zone helpers unblock overrides.
3. **Finish with group B** – return updated flags/metadata so the ViewModel keeps
   ownership of UI notifications.
4. Keep `_using_project_overrides` flag in the ViewModel until Sprint 28 when we
   can hand it to `StateManager`.

## Deferred / Out of Scope

- `apply_project_model_overrides`, `save_project_model_overrides`, and
  `apply_project_settings_to_batch` remain for Sprint 28 due to high coupling.
- Observer/UI helpers such as `_on_project_state_changed` stay inside
  `MainViewModel`.

## Next Actions

1. Wire `ProjectOrchestrator` inside `__main__.py` (composition root) with the
   required callbacks.
2. Add integration tests that cover:
   - Project open/close lifecycle
   - Model override roundtrip (save → apply → revert)
   - Asset removal flows
3. Schedule Sprint 28 to finish the high-risk override/batch helpers once the
   orchestrator façade is stable.
