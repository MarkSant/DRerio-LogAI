# v8 Phase 0 Audit — generic class roles and analysis windows

**Date:** 2026-10-30 · **Base:** `feat/generic-class-aliases` @ `5fa0f8d2` · **Mode:** read-only

Six parallel audits (detection/plugins/weights; UI; live + Arduino; recording/analysis/reports;
time & frame semantics; i18n/docs/tests) mapped every component that produces, transforms,
persists, reads or displays **class** data, and every component whose meaning depends on
**time zero**. This file is the consolidated result; the decisions it led to are in
[ADR-009](ADR-009-class-roles.md) … [ADR-013](ADR-013-zebrafish-compatibility.md).

## Flow legend

| Code | Flow |
|---|---|
| SV | single video (no project) |
| PR | pre-recorded project (batch worker) |
| LP | live project (Progress grid / legacy panel button) |
| LA | live ad hoc (`LiveAnalysisDialog`) |
| MAs / MAp | multi-aquarium, sequential / parallel |
| RP | reprocessing / report regeneration |
| MT | model test & diagnostics menus (in and out of a project) |
| WZ | project wizard |

Risk column = risk of a **silent** failure (plausible output, wrong numbers).

## 1. Matrix — class data

| Component (file:line) | Assumption today | Flows | Silent risk | Covering test |
|---|---|---|---|---|
| `core/video/processing_worker.py:171-216, 648-661` | Model path built from `settings.weights.<persp>.det_filename`; ignores `WeightManager`, project `model_overrides`, OpenVINO hash | SV PR MAs MAp RP | **High** — the chosen rat weight is silently swapped for the zebrafish default | none |
| `core/services/weight_manager.py:54-61, 340-343, 397-398` | Target derived from type (det→aquarium, seg→zebrafish); step-2 fallback picks the first weight of the same perspective by JSON order | LP LA WZ MT | **High** — two top-down det weights race by insertion order | `tests/core/test_weight_manager_targets.py` (not the race) |
| `core/services/weight_manager.py:1406-1420, 1586-1597` | OpenVINO cache keyed by basename, reused without checking the `.pt` | all with OpenVINO | **High** — retrained weight with the same name reuses the old export and old `metadata.json` | none |
| `core/detection/single_detector.py:386-394`, `zone_scaler.py:453-483` | Inference runs only on the arena crop (+10 px); no polygon → `[]` | all | **High** for triggers — experimenter outside the crop is never seen | none |
| `core/detection/single_detector.py:397` | Raw all-class predictions exist only here, then are filtered away | all | hook point (A/B) | none |
| `core/detection/single_detector.py:399-411` | Polygon filter applied to every class | all | Medium — context outside the arena dropped | none |
| `core/detection/detection_post_processor.py:188-209` | `apply_class_mismatch_fallback`: small arena box → animal | single-arena flows | Medium-high — partially occluded arena becomes a "ghost rat" | `test_detection_post_processor_extended.py::test_apply_class_mismatch_fallback` |
| `single_detector.py:419-420`, `multi_aquarium_detector.py:510, 600` | Exactly one subject class (`==`) | all | Medium — extra subject classes silently dropped | `tests/core/test_class_aliases.py::test_lowest_id_wins_when_several_animal_names` |
| `core/detection/class_aliases.py:299-324`, `plugins/openvino_detector.py:363-393` | Positional fallback 0/1; OpenVINO without `metadata.json` → `class_i` | OpenVINO; unknown names | **High** — on Barnes, "animal" = experimenter | `tests/test_class_names_validation.py::test_openvino_plugin_fallback_without_metadata` |
| `core/services/detector_service.py:1093-1117` | Class validation only logs | LP LA | **High** — the natural gate lets everything through | `tests/test_class_names_validation.py::test_validate_model_classes_missing_animal_class_warns` |
| `plugins/openvino_detector.py:776-781` vs `ultralytics_detector.py:165-172` | OpenVINO NMS is class-agnostic; Ultralytics is per class | all | Medium-high — rat inside `start_box` suppressed only on OpenVINO | none |
| `ultralytics_detector.py:57,169`, `openvino_detector.py:147,778` | One confidence (animal's) for every class | all | Medium — low-confidence context classes vanish | none |
| `io/recorder.py:875` | `class_id` received and discarded | all | High if a context box ever reaches the writer (becomes a subject) | `tests/test_recorder.py::test_immutable_schema_unchanged_by_mask_feature` |
| `io/recorder.py:1228, 1402` | Dedup by `(frame, track_id)` collapses `track_id=None` rows | all | High for untracked detections | none |
| `core/recording/frame_processing_pipeline.py:945` | Writes only when there are detections | LP LA | Medium — absence ≡ "frame not analysed" | none |
| `core/recording/frame_processing_pipeline.py:1316-1324`, `arduino_event_mapper.py:8-10` | ROI occupancy = any box, no class/track filter | LP | Medium — any subject class fires | `tests/core/test_arduino_zone_dispatch.py` |
| `core/project/project_workflow_service.py:731-752` | Wizard method stored only in `_wizard_metadata`; reopen uses the global | PR LP RP | **High** — chosen seg/det method lost on reopen | none |
| `ui/components/canvas/renderer.py:524-547`, `video_frame_manager.py:367-398` | `class_id == 0` painted as "Aquarium"; no colour/label for other roles; `"Alvo"` outside `_()` | all (display) | Medium | none |
| `ui/components/global_model_configuration_panel.py:545-581` | "Change Target" branches on typed text; only aquarium/zebrafish | MT | Medium | none |
| `ui/wizard/model_selection_step.py:407-423, 1230-1287` | Two fixed roles (arena, animal) | WZ | Medium — no way to map 4 classes | `tests/ui/wizard/test_model_selection_step.py::test_get_data_returns_complete_configuration` |
| `core/project/parquet_io_manager.py:747` | Import copies only the trajectory | import | High for any sidecar | `tests/test_parquet_import.py` |
| `io/recorder.py:318-328, 1123` | `start_recording` keeps a stale `3b_Mascaras` | RP | **High** — masks from another run joined by `(frame, track_id)` | none |
| `core/services/mask_capture.py:55` | Decides by global `animal_method`, not the effective weight's task | masks | Low | `tests/core/services/test_mask_capture_extended.py` |

## 2. Matrix — time and frame

| Component (file:line) | Assumption today | Flows | Silent risk | Covering test |
|---|---|---|---|---|
| `coordinators/report_generation_coordinator.py:180, 415, 672, 747`; `core/video/analysis_pipeline_runner.py:378` | `fps = settings.video_processing.fps` (30), never the video's fps | all reports, RP | **Critical** — Barnes (VFR ~9.9 fps) treated as 30 fps; up to 125 s drift | none |
| `analysis/analysis_service.py:368-373`, `trajectory_validator.py:332` | `duracao_video_s = len(df) / fps` (rows, not time) | all | **Critical** — `video_duration_s` (the normalisation column) wrong whenever N > 1 or tracks ≠ 1 | golden (N = 1 masks it) |
| `analysis/roi.py:97-110, 1191` | Latency t0 = first detected row; `bool.diff()` is XOR, so an exit counts as the first entry | all | **Critical** — the golden already shows `latencia_primeira_entrada.Esquerda = None` with 1 entry | `tests/analysis/test_roi_extended.py::test_latency_to_first_entry` (starts outside only) |
| `analysis/visualization_generator.py:1009-1178`; `reporters/word_reporter.py:455-472`; `behavior.py:1182, 1246` | Time axes, event log and `percentage_of_recording` start at the first detection | all | Medium | none |
| `core/video/processing_worker.py:1260` | Pre-recorded `timestamp` = `POS_MSEC/1000` (PTS) — correct for VFR | PR SV | Low | `tests/integration/test_prerecorded_golden.py` (CFR only) |
| `core/video/processing_worker.py:1206-1218` vs `frame_processing_pipeline.py:408` | `processing_offset` documented but ignored; pre-recorded samples 0, N, 2N; live samples N, 2N | PR LP | Medium | none |
| `core/video/video_context_factory.py:67` | Real fps read and then dropped before analysis | PR | **High** | none |
| `core/recording/frame_processing_pipeline.py:956` | Live `timestamp` = processing clock (after queue + inference) | LP LA | High for any event dating | `tests/core/recording/test_frame_timeline_reconstruction.py` (ledger only) |
| `frame_processing_pipeline.py:384-390, 408, 873`; `io/camera.py:324` | Duplicate frames from polling; two decimation cadences (N … N²) | LP LA | High for frame-counted persistence | none |
| `io/recorder.py:171, 334-339` | Live MP4 written at nominal 30 fps while the camera delivers 39–41 fps | LP LA RP | High — re-tracking the MP4 yields another time base | none |
| `frame_processing_pipeline.py:1496-1508` | `_clear_queues` drops the tail without ledger rows | LP LA | High — silent end truncation | `test_frame_processing_pipeline_extended.py::test_clear_queues` |
| `core/recording/live_session_manager.py:842-853` | "50 % heuristic": an early stop without `keep_data` writes `.cancelled` and deletes the project polygon | LP | **High** with a condition-driven stop | `tests/core/recording/test_live_session_stop_intent.py` |
| `core/main_view_model.py:421-446` | Arduino code 0 routed to the legacy coordinator once the grid session is active → ignored | LP | **High** | marshalling only |
| `io/arduino_manager.py:585-617` | Arduino events carry no timestamp | LP | High for dating a START | none |
| `core/detection/detection_post_processor.py:410-421` → `tracker/byte_tracker.py:226` | ByteTrack `frame_rate` = settings fps (30) | all | Medium — buffer 3× longer at 9.9 fps | `tests/core/test_detection_post_processor.py::test_fps_default_and_value` |
| `core/recording/live_analysis_post_processor.py:1189-1193` | Multi-aquarium live calls `write_partitioned_detection_data` with wrong kwargs; parent `start_time` never set | LP (multi) | **Critical if reachable** — no rows written | none |

## 3. Behaviour defaults inherited from zebrafish

| Component | Assumption | Note |
|---|---|---|
| `settings.py:1192` | `aquarium_perspective="lateral"` default → geotaxis computed for top-down rodents | follow-up issue |
| `settings.py:1168-1172` | Thigmotaxis distance capped at 10 cm | follow-up issue |
| `analysis/trajectory_validator.py:43` | Max plausible speed 50 cm/s "for zebrafish" | warning only |
| `analysis/behavior.py:786-826` | Freezing: `fillna(0)` makes row 0 frozen; blocks span tracking gaps | follow-up issue |
| `analysis/analysis_service.py:357` | Total distance sums jumps across gaps | follow-up issue |

## 4. Persistence contracts that must NOT be renamed

`weights_config.json` targets `aquarium`/`zebrafish` and the four `is_default_<m>_<t>` flags;
`project.json` keys `num_aquariums`, `animals_per_aquarium`, `aquarium_*`,
`preserve_real_aquarium_shape`, `multi_aquarium_outputs`, `single_animal_per_aquarium`;
the `aquarium_id` Parquet column; `aquarium_{N}/` output folders; the `Aquarium` xlsx column;
`aquarium_perspective`; everything in `scripts/i18n_allowlist.txt`.

Output-prefix map (actual, not the outdated CLAUDE.md one): `1_ProcessingArea_`,
`2_AreasOfInterest_`, `3_CoordMovimento_`, `3b_Mascaras_`, `4_Relatorio*`, `5_ClosedLoop_`,
`5_RelatorioIndividual_`, `6_FrameLedger_`. Free: `3c_`, `7_`. Several readers glob
`3_CoordMovimento_*` and take `[0]` or test `startswith("3_CoordMovimento")`, so no new file may
start with that string.

## 5. Coverage gaps relevant to v8

- `core/detection/class_aliases.py` is missing from `scripts/mutation_catalog.yaml`.
- No test asserts that every `_()` msgid is in the `.pot` (the `.pot` is 40 msgids behind `.po`).
- No frozen 7.2.0 project fixture (legacy dicts are inlined in tests).
- No multi-class synthetic video; `tests/helpers/prerecorded_pipeline.py` is the base to extend.
- `hypothesis` is available and used in 14 files.

## 6. Barnes protocol facts (lab reference, MATLAB TrackGUI)

- Top view, 1 animal, 1 arena; px/cm from the 184 cm diameter.
- START today: manual, animal released and experimenter out of view (≈ 6.7 s in `Exemp_1`,
  ≈ 3.1 s in `Exemp_2`).
- END: four paws in the escape box, or 240 s (censored).
- Processing rate = every frame (`analysis_interval_frames = 1`).
- Sample videos: H.264 640×428, VFR, avg 9.90 / 9.89 fps, 546 / 1846 frames,
  55.127 / 186.608 s; frame interval 98–142 ms. Using `frame / 30` drifts up to 125 s; PTS is exact.
