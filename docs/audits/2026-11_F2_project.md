# F2 — `core/project/` coverage front (TASK-087)

Scope: `src/zebtrack/core/project/` (15 files). Method: real `ProjectManager` projects on
`tmp_path` (created, edited and reloaded from `project_config.json`), real zone parquets read
back with pandas, a real `ZoneManager` registry behind every callback, and one mutation block
per module in `scripts/mutation_catalog.yaml` (section `core/project coverage (TASK-087)`).
Every expected value is derived from the test input.

## Defects

| id | `file:line` | what is wrong | evidence | status |
| --- | --- | --- | --- | --- |
| F2-P-001 | `core/project/asset_manager.py:978` (`remove_video_entry`) | With `delete_files=True` the method `rmtree()`s the video's PARENT folder ("force delete subject folder"). A pre-recorded project registers videos where they already are, so several videos usually share one folder: removing one video (or one subject/day/group through `remove_subject`, which passes `delete_files` from the tree dialog) deletes every sibling video and file in that folder. | `test_removing_one_video_keeps_its_sibling_in_the_same_folder`: two videos in one folder, remove `a.mp4` with `delete_files=True`, `b.mp4` no longer exists. Fixed: only this video's zone parquets (exact names, current and legacy prefixes) are deleted, and the folder is removed only when nothing is left in it; a live session folder still goes through its registered `results_dir`. Tests: sibling kept, emptied folder removed, project root untouched; mutation block `asset_manager_video_removal_scope`. | fixed |
| F2-P-002 | `core/project/metadata_manager.py:213-225` (`save_detector_state`) | `last_updated` is stamped into `detector_config` before `elif not detector_config` is evaluated, so that branch can never run: saving an empty detector config never clears `model_overrides.detector_parameters`, and stale thresholds keep being applied. | `test_saving_an_empty_detector_config_clears_the_threshold_overrides`: overrides `{"nms_threshold": 0.4}` survive `save_detector_state({})`. Fixed: emptiness is read before the stamp; a config without threshold keys still leaves the overrides alone (new test). No production caller passes `{}` today. Block `metadata_manager_empty_detector_config`. | fixed |
| F2-P-003 | `core/project/output_registration_manager.py:292` (`derive_processing_metadata`) | The wizard-regex fallback builds `MultiAquariumData(enabled=True, aquarium_configs=[])`; the model rejects it ("requires exactly 2 aquarium configurations"), the `ValidationError` is a `ValueError` and is swallowed by the `except (re.error, ValueError, KeyError)`. The fallback therefore never fills group/day/subject, and such videos land in `Grupo_Sem_Grupo/...`. Not fixed here: fixing it moves where results of existing projects are written. The same construction exists in `coordinators/multi_aquarium_coordinator.py:344` (out of scope, not verified). | `test_entry_values_and_the_wizard_regex_fill_the_gaps`: `G2_D3_S4.mp4` with `G(\d+)/D(\d+)/S(\d+)` gives no `group`. Reproduced directly: `MultiAquariumData(enabled=True, regex_pattern=..., aquarium_configs=[])` raises. Fixed in both sites with `enabled=False` (only the regex is read; `ProjectLifecycleManager` already stores the wizard regex as a disabled config). Effect: a video whose entry lacks group/subject now gets them from the wizard regex instead of `Grupo_Sem_Grupo`; outputs already written are not moved. The coordinator site was verified: the assignment dialog now gets the regex prefill (`test_wizard_regex_reaches_the_assignment_dialog`). Blocks `output_registration_wizard_regex`, `multi_aquarium_assignment_wizard_regex`. | fixed |
| F2-P-004 | `core/project/zone_orchestration_manager.py:103` (`sync_active_zone_video`) | The docstring says disk parquets are MERGED into incomplete in-memory zones, but the disk `ZoneData` is saved over the memory one: an in-memory arena is lost when only the ROI parquet exists on disk. | `test_rois_on_disk_keep_the_arena_already_in_memory`: memory arena `SQ`, disk ROI-only parquet, after sync the polygon is `[]`. Fixed: `merge_disk_into_memory()` keeps every part already in memory (arena; ROI polygons/names/colours; metadata keys) and takes only the missing ones from disk. Block `zone_orchestration_disk_merge`. | fixed |
| F2-P-005 | `core/project/project_service.py:198` (`save_project_config`) | The integrity hash was computed over the in-memory dict; JSON writes non-string keys as strings and `sort_keys` orders ints numerically but strings lexically, so `{2: .., 10: ..}` hashed differently from the `{"10": .., "2": ..}` read back, and the project failed its own integrity check (`IntegrityError`) on the next open. | `TestIntegrityRoundTrip.test_integer_keys_survive_a_save_and_load` was red (`IntegrityError`); green after hashing the JSON-normalised data. String-keyed projects hash identically, so existing files still validate (legacy 7.2 fixture test passes). Mutation `project_service_integrity/hash-over-memory` guards it. | fixed |

## Observations (not defects)

| id | `file:line` | observation | status |
| --- | --- | --- | --- |
| F2-P-O1 | `core/project/asset_manager.py:986` | The empty-ancestor cleanup after deleting a video reads `project_data["project_path"]`, a key nothing writes, so it never runs. | reported |
| F2-P-O2 | `core/project/asset_manager.py:972` | Zone parquets are globbed as `2_ZonasROI_*`, a prefix the recorder no longer writes (`2_AreasOfInterest_*`); harmless only because the whole folder is removed right after (see F2-P-001). Superseded by the F2-P-001 fix, which deletes `1_ProcessingArea_`, `2_AreasOfInterest_` and the legacy `2_ZonasROI_` by exact name. | fixed |
| F2-P-O3 | `core/project/zone_orchestration_manager.py:324` | `clear_zone_data_for_video` refreshes the last-zone pointer on a throw-away `ZoneManager()`, not the project's; `get_last_zone_video` re-validates the pointer, so no wrong value reaches a caller. | pinned |
| F2-P-O4 | `core/project/video_manager.py:292` (`add_video_batch`) | Duplicate of `ProjectLifecycleManager.add_video_batch`, which is the one `ProjectManager` uses; tested, not removed. | reported |

## Not covered on purpose

- Symbols the A2 audit lists as dead (`ensure_roi_template_dir`, `has_*_for_aquarium`,
  `set/get_arena_for_video`, `set/get_rois_for_video`, `_validate_project_parameters`,
  `load_metadata_csv`, `save_model_overrides`, `save_arena_polygon`, `ROITemplateManager.load_template`,
  `cleanup_orphaned_templates`, `delete_template`, `refresh_complete_flag`,
  `update_entry_zone_flags`): no new tests; existing ones were kept.
- A5 silent failures in this package (`zone_manager.py:998`, `project_service.py:364`,
  `metadata_manager.py:79`): untouched.
