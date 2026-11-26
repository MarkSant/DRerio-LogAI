# Interface terminology per animal model (Barnes v8.1, stage 3)

Issue #633, plan `PLAN.md` Part I §6. The interface began as a zebrafish/aquarium
tracker, so it said "aquarium" and "fish" everywhere. A rat on a Barnes table is not in an
aquarium. Stage 3 makes the **displayed** vocabulary follow the project's animal model,
starting with the most visible surfaces, and changes nothing else.

## The rule that governs everything

| | |
| --- | --- |
| Persisted keys, folders, files, JSON/parquet keys, weight targets | **Never renamed** (ADR-012): `num_aquariums`, `animals_per_aquarium`, `aquarium_width_cm`, `aquarium_height_cm`, `aquarium_id`, `is_multi_aquarium`, `aquarium_perspective`, `aquarium_N/`, `{exp}_aq{N}_summary.parquet`, weight targets `aquarium` / `zebrafish`. |
| Displayed text | Follows `animal_model` through `ui/terminology.py`. |
| Zebrafish, `other`-less legacy projects (no profile) | Read **exactly today's text**, byte for byte: the `zebrafish` variant of every key is the original msgid, so the existing pt_BR translations keep applying (guarded by `tests/ui/test_terminology.py`). |

## The API (`src/zebtrack/ui/terminology.py`)

```python
from zebtrack.ui.terminology import term, animal_model_of, animal_model_of_gui

term("zones.detect_button", animal_model)             # "Detect Arena (Auto)" for a rodent
term("subject.label", animal_model, label="03")       # "🐀 Subject 03"  (format args optional)
animal_model_of(project_data, behavioral_config)      # AnimalModel, through resolve_experiment_profile
animal_model_of_gui(gui)                              # the open project's model; zebrafish when none
```

- `term(key, animal_model=None, /, **fmt)` — `animal_model` is an `AnimalModel`, its token
  (`"rodent"`) or `None`. `None`/`zebrafish` → legacy text. `rodent` → the neutral
  "arena"/"animal" wording. `other` → like `rodent` unless the entry gives it its own text
  (only the emoji differ today: 🐟 zebrafish, 🐀 rodent, 🐾 other). An unknown token degrades to
  `other` (same as the profile resolver); an unknown **key** raises `KeyError`, so a typo never
  reads as legacy.
- `term_keys()` and `variants(key)` list the vocabulary (used by the tests).
- Callers get the model from `resolve_experiment_profile` (via `animal_model_of*`), from the
  wizard's collected `behavioral_analysis` block (`WizardStep._animal_model()`), or from a
  widget's own current selection (`BehavioralConfigWidget` / the ad-hoc dialogs'
  `_profile_animal`). Nothing here reads the profile keys itself.

### Rules (all enforced by tests or review)

1. **One complete msgid per animal variant.** Portuguese inflects ("o aquário" / "a arena",
   "Arena Ativa", "apenas 2 arenas são suportadas"). Never splice a translated noun into another
   translated sentence; each variant of a key is a whole sentence a translator can read.
   `tests/ui/test_terminology.py` checks every variant carries the same `{fields}`.
2. **Call time, never import time.** The registry is built inside a cached function of
   per-key thunks, so `_()` runs when `term()` is called (`tests/i18n/test_no_import_time_translation.py`).
   Widgets built once keep a reference and re-word in `_apply_terms()` when the profile changes.
3. **Never branch on displayed text.** Compare tokens (`AnimalModel`), never what `term()`
   returned.
4. **Help text that quotes a button quotes ITS button.** `zones.no_frame`,
   `zones.no_arena_live_prompt` and `zones.no_arena_live_steps` embed the Detect button's label
   per variant; a test asserts `'<term("zones.detect_button", model)>'` appears in each.
5. **Watch the i18n gotchas** (`docs/guides/developer/i18n.md`): no `_` as a throwaway, a new
   msgid that collides with an existing one is dropped by `i18n_pairs.py` (the new variants all
   use msgids that did not exist), the allowlist matches by substring (nothing was added to it).

### Adding a key

1. Add `"<surface>.<what>": lambda: _Entry(_("legacy msgid"), _("neutral msgid"))` inside
   `_entries()` (third argument only for a species-specific variant). The legacy msgid is the
   string the screen used before, unchanged.
2. Call `term("<key>", animal_model, **fmt)` where the string was.
3. If the widget outlives the profile, keep a reference and re-word it when the profile changes.
4. Catalogue: put `{neutral msgid: pt_BR}` in `src/zebtrack/locales/_pairs/barnes-animal-terms.json`
   and append the entries to `zebtrack.pot` / `pt_BR/.../zebtrack.po` by hand (a regeneration drags
   ~2600 unrelated lines, see the "stale catalogue" gotcha), then
   `python scripts/compile_translations.py`. `tests/i18n` verifies sync.

## Migrated surfaces (before → after)

All rows: zebrafish/legacy = the left column, unchanged. "Rodent" also applies to a Barnes
project (Barnes forces the rodent model); `other` reads the same except for the emoji rows.

| Surface | Key | Zebrafish / legacy (EN → pt_BR) | Rodent / Barnes (EN → pt_BR) |
| --- | --- | --- | --- |
| Wizard · Calibration | `calibration.count_label` | Number of aquariums (videos): → Número de aquários (vídeos): | Number of arenas (videos): → Número de arenas (vídeos): |
| | `calibration.animals_label` | Animals per aquarium: → Animais por aquário: | Animals per arena: → Animais por arena: |
| | `calibration.count_help`, `calibration.animals_help` (tooltips) | "Each aquarium = 1 separate video", "(e.g. a zebrafish shoal)" | "Each arena = 1 separate video", "(e.g. a large social group)" |
| Wizard · Discovery glossary | `discovery.glossary` | "Arena: the area of the tank where the animals move" | "Arena: the area where the animals move, such as a table or a box" (re-worded when the animal combo changes) |
| Wizard · Detection / Confirmation summaries | `wizard.count_summary`, `wizard.animals_summary`, `wizard.arena_method_summary`, `wizard.arena_weight_summary` | • Aquariums: N · • Animals per aquarium: N · • Aquarium method/weight: … → • Aquários / • Animais por aquário / • Método aquário / • Peso aquário | • Arenas: N · • Animals per arena: N · • Arena method/weight: … → • Arenas / • Animais por arena / • Método da arena / • Peso da arena |
| Behavioural configuration widget (Calibration step, live and single-video dialogs) | `behavioral.perspective_title` | Aquarium Perspective `*` → Perspectiva do Aquário `*` | Arena Perspective `*` → Perspectiva da Arena `*` |
| | `behavioral.perspective_help` | Select how the camera sees the aquarium: | Select how the camera sees the arena: → Selecione como a câmera visualiza a arena: |
| | `behavioral.thigmotaxis_help` | …considering the fish close to the aquarium walls: | …considering the animal close to the arena walls: → …considerar o animal próximo às paredes da arena: |
| | `behavioral.zones_split` | Split the aquarium into: → Dividir aquário em: | Split the arena into: → Dividir a arena em: |
| Zones tab | `zones.detect_button` | Detect Aquarium (Auto) → Detectar Aquário (Auto) | Detect Arena (Auto) → Detectar Arena (Auto) |
| | `zones.active_frame` | 🐟 Active Aquarium → 🐟 Aquário Ativo | 🐀 Active Arena → 🐀 Arena Ativa (other: 🐾) |
| | `zones.radio_left/right`, `zones.sequential_radio`, `zones.sequential_help` | Aquarium 1 (Left) … 1 aquarium at a time | Arena 1 (Left) … 1 arena at a time → Arena 1 (Esquerda) … 1 arena por vez |
| Messages quoting the button | `zones.no_frame`, `zones.no_arena_live_prompt`, `zones.no_arena_live_steps` | …use 'Detect Aquarium (Auto)'… | …use 'Detect Arena (Auto)'… |
| Live analysis dialog (no project) | `live.count_label/help`, `live.animals_label/help`, `live.one_arena_notice`, `live.count_error` | No. of aquariums: / Animals/aquarium: / Live analysis handles ONE aquarium… | No. of arenas: / Animals/arena: / …ONE arena… → Nº de arenas: / Animais/Arena: / …UMA arena… (follows the dialog's animal combo) |
| Single-video dialog | `single.count_label/help`, `single.animals_label/help` | Number of Aquariums: / Animals per Aquarium: (+ tooltips, "e.g. tanks") | Number of Arenas: / Animals per Arena: |
| Aquarium assignment dialog (2 arenas in one video) | `assignment.title/header/panel_title/excess_matches/group_empty/subject_empty` | Aquarium Configuration / Aquarium 1 (Left) / The group of Aquarium 1 cannot be empty | Arena Configuration / Arena 1 (Left) / The group of Arena 1 cannot be empty |
| Subject nodes in the project trees (`validation_manager`, `report_tree_builder`, `video_selector_tree_manager`) and the block dialog title | `subject.label`, `subject.list_title` | 🐟 Subject 03 → 🐟 Sujeito 03 · 🐟 Subjects → 🐟 Cobaias | 🐀 Subject 03 → 🐀 Sujeito 03 · 🐀 Subjects → 🐀 Cobaias (other: 🐾) |

### Reports (display mapping only, `analysis/data_transformer.py`)

- `display_metadata_label(key, animal_model)` — the Word report's "Experiment Metadata" block
  title-cases the raw metadata keys. Zebrafish/legacy: byte-identical (`Num Aquariums`,
  `Animals Per Aquarium`, `Aquarium Width Cm`). Rodent/other: the aquarium fragment of the
  **key** is re-worded (`Num Arenas`, `Animals Per Arena`, `Arena Width Cm`). The labels are
  English, as before (they were never translated).
- `display_column_name(column, animal_model)` — the Word summary table; `DISPLAY_COLUMN_MAPPING`
  is untouched, with `aquarium_id` → `Arena` only for rodent/other; an unmapped column falls back to
  the title-cased key with the same aquarium → arena re-wording (`Arena Perspective`).
- `DataTransformer.prepare_for_display(..., animal_model=...)` — same override for the
  `.xlsx` (individual report: `ExcelReporter` passes the run's model). Internal column keys never
  change. The unified/partial report (`_unified_report_mixin`) does not know the profile and keeps
  `Aquarium`; multi-aquarium is refused for Barnes anyway.

## Not migrated (inventory for a later pass)

`file:line` of every remaining `_()` msgid that mentions aquarium/fish/tank, grouped by
surface. Regenerate with the AST script in the stage-3 hand-over (walk `src/zebtrack`, `_()` calls
whose first argument matches `aquari|fish|🐟|tank`). Notes:

- **Coordinators are outside this stage's file ownership.** Two of them quote the Detect
  button by its legacy label and therefore read "Detect Aquarium (Auto)" next to a rodent
  project's "Detect Arena (Auto)": `coordinators/dialog_coordinator.py:237` and
  `coordinators/live_calibration_coordinator.py:1080` (also the "Draw the Aquarium" /
  "Aquarium Detected" dialog titles of `live_calibration_coordinator`). **Highest priority** for the
  next pass; use `term("zones.detect_button", animal_model_of(project_data))` or add keys.
- The `zebrafish`-labelled model choice `Zebrafish (aquarium)` (`behavioral_config_widget.py`) is the
  *name of the animal model* and stays. `global_model_configuration_panel.py` already maps the
  stored weight target `aquarium` to "Arena" (the precedent), and its help sentence still says
  "aquarium or zebrafish".
- `project_overview.py:503` keeps `🐟 Subject {label}` only as the fallback of `subject.get("label", …)`;
  `ValidationManager` always supplies the label (migrated).
- Multi-aquarium-only text (`Aquarium {number}` canvas labels, delete-aquarium menus, sequential
  coordinators) is reachable only for two-arena videos; Barnes refuses multi-aquarium.

### Wizard steps (10)

- `ui/wizard/calibration_step.py:186` — '📏 Arena Width (horizontal axis)\n\nThe REAL physical size of the arena visible in the video, in centimetre...
- `ui/wizard/calibration_step.py:218` — '📏 Arena Height (vertical axis)\n\nThe REAL physical size of the arena visible in the video, in centimetres...
- `ui/wizard/live_config_step.py:423` — Preserve the real aquarium shape (segmentation)
- `ui/wizard/live_config_step.py:429` — Preserve the real aquarium shape ⏎  ⏎ When enabled, keeps the real polygon (N vertices) detected by the YOL...
- `ui/wizard/live_config_step.py:612` — Supported aquariums: {count} ⏎ Multi-aquarium in real time may not be possible.
- `ui/wizard/live_config_step.py:1010` — Aquarium Limit
- `ui/wizard/live_config_step.py:1011` — ⚠️ Simultaneous recording is limited to 2 aquariums. ⏎  ⏎ Your project has {count} aquariums configured. ⏎ ...
- `ui/wizard/live_config_step.py:1022` — A project with {count} aquariums exceeds the limit of 2 for simultaneous recording.
- `ui/wizard/live_config_step.py:1032` — Mode selection cancelled. Adjust the number of aquariums or select a compatible mode.
- `ui/wizard/model_selection_step.py:650` — 🔗 Match Threshold ⏎  ⏎ Tolerance when associating boxes. ⏎ HIGH values (close to 1.0) are more permissive f...

### Zones canvas (drawing, overlay, renderer) (13)

- `ui/components/canvas/multi_aquarium_overlay.py:41` — Aquarium 1
- `ui/components/canvas/multi_aquarium_overlay.py:46` — Aquarium 2
- `ui/components/canvas/multi_aquarium_overlay.py:236` — Detected {count} aquariums successfully! ⏎ Check that the markings are correct.
- `ui/components/canvas/multi_aquarium_overlay.py:267` — Add a Second Aquarium
- `ui/components/canvas/multi_aquarium_overlay.py:268` — Polygon saved successfully! ⏎  ⏎ Does this video have two aquariums? ⏎ If so, you will be able to draw the ...
- `ui/components/canvas/multi_aquarium_overlay.py:330` — Draw the polygon of Aquarium 2. ⏎ The polygon of Aquarium 1 is shown as a reference.
- `ui/components/canvas/renderer.py:389` — Aquarium {number}
- `ui/components/canvas/renderer.py:606` — Aquarium 1 (reference)
- `ui/components/canvas/video_frame_manager.py:567` — Please choose an item with a fish icon (🐟) to load the frame.
- `ui/components/canvas/zone_editor.py:347` — Drawing: Aquarium {number} of 2
- `ui/components/canvas/zone_editor.py:622` — Arena of Aquarium {number} saved successfully.
- `ui/components/canvas/zone_editor.py:631` — Next Aquarium
- `ui/components/canvas/zone_editor.py:632` — Arena of Aquarium {saved} saved. ⏎ Now draw the arena of Aquarium {next}.

### Dialogs (25)

- `ui/dialogs/aquarium_detection_progress_dialog.py:93` — Detecting Aquarium
- `ui/dialogs/aquarium_detection_progress_dialog.py:124` — ⏳ Detecting the Aquarium Automatically
- `ui/dialogs/aquarium_detection_progress_dialog.py:132` — Session: {experiment} ⏎ Analyzing frames to identify the aquarium region...
- `ui/dialogs/aquarium_detection_progress_dialog.py:255` — ✓ Aquarium detected (valid area)
- `ui/dialogs/block_detail_dialog.py:1766` — Partial reports generated successfully! ⏎  ⏎ 📊 Excel: {excel} ⏎ 📝 Word: {word} ⏎ 🐟 {count} aggregated sessions
- `ui/dialogs/block_detail_dialog.py:2054` — Batch '{block}' marked as complete. ⏎  ⏎ 📊 Excel: {excel} ⏎ 📝 Word: {word} ⏎ 🐟 {count} aggregated sessions ...
- `ui/dialogs/live_analysis_dialog.py:646` — Real HEIGHT of the arena, in centimetres — the vertical extent as the camera sees it. ⏎  ⏎ For a top-down v...
- `ui/dialogs/live_camera_mode_selection_dialog.py:67` — Parallel Real-Time Processing ⏎ • Detects 2-6 aquariums simultaneously ⏎ • Requires a GPU and ≥4 CPU cores ...
- `ui/dialogs/live_camera_mode_selection_dialog.py:73` — Single Aquarium in Real Time ⏎ • Processes 1 aquarium at a time ⏎ • Requires ≥2 CPU cores ⏎ • Ideal for sys...
- `ui/dialogs/live_camera_mode_selection_dialog.py:79` — Sequential Sessions ⏎ • Records N separate sessions, one at a time ⏎ • Processes each aquarium in real time...
- `ui/dialogs/live_camera_mode_selection_dialog.py:155` — Your system does not support real-time processing of {count} aquariums simultaneously. ⏎  ⏎ Review the opti...
- `ui/dialogs/live_camera_mode_selection_dialog.py:216` — CPU: {cores} cores ({usage}% used) ⏎ RAM: {available} GB available of {total} GB ⏎ GPU: {gpu} ⏎ Supported a...
- `ui/dialogs/live_camera_mode_selection_dialog.py:333` — Parallel Multi-Aquarium
- `ui/dialogs/live_camera_mode_selection_dialog.py:334` — Single Aquarium
- `ui/dialogs/preview_polygon_dialog.py:54` — No aquarium found at this threshold. Lower it and try again.
- `ui/dialogs/preview_polygon_dialog.py:146` — Aquarium Detected - Confirm?
- `ui/dialogs/preview_polygon_dialog.py:185` — Aquarium Detected - Confirm?
- `ui/dialogs/preview_polygon_dialog.py:212` — ✓ Aquarium detected successfully!
- `ui/dialogs/preview_polygon_dialog.py:362` — Aquarium re-detected with threshold {value}
- `ui/dialogs/preview_polygon_dialog.py:453` — Aquarium Detected
- `ui/dialogs/welcome_dialog.py:154` — 'Six models are installed. Four are specialists, trained for one camera angle each: segmentation and detect...
- `ui/dialogs/zone_calibration_dialog.py:76` — How do you want to define the aquarium zone?
- `ui/dialogs/zone_calibration_dialog.py:98` — Will try to detect the aquarium automatically over 10 frames
- `ui/dialogs/zone_calibration_dialog.py:118` — You will draw the aquarium polygon manually
- `ui/dialogs/zone_reuse_dialog.py:85` — Zones have already been defined. ⏎  ⏎ Do you want to reuse them for this recording? ⏎ (Use this if the aqua...

### Other UI components (25)

- `ui/components/arduino_bindings_panel.py:155` — Aquarium
- `ui/components/arduino_bindings_panel.py:172` — Aquarium:
- `ui/components/arduino_bindings_panel.py:180` — All = this ROI in any aquarium
- `ui/components/arduino_bindings_panel.py:539` — {roi} (aquarium {number})
- `ui/components/behavioral_config_widget.py:46` — Zebrafish (aquarium)
- `ui/components/behavioral_config_widget.py:480` — Frames faster than this are flagged as implausible. 50 cm/s suits adult zebrafish; rodents sprint faster.
- `ui/components/dialog_manager.py:877` — No arena for {name} — detecting the aquarium first...
- `ui/components/global_model_configuration_panel.py:234` — Ctrl/Shift-click to select several. Type = how the model operates (segmentation or detection); Target = wha...
- `ui/components/menu_manager.py:222` — Automated behavioral tracking and analysis ⏎ for research with Danio rerio (zebrafish) ⏎  ⏎ Computer vision...
- `ui/components/menu_manager.py:480` — This video holds data from {count} separate aquarium(s). ⏎  ⏎ ⚠️ WARNING: Removing the video permanently de...
- `ui/components/menu_manager.py:489` — This video holds data from {count} separate aquarium(s). ⏎  ⏎ ⚠️ Removing this item affects the data of ALL...
- `ui/components/project_overview.py:503` — 🐟 Subject {label}
- `ui/components/project_views/report_tree_builder.py:639` — Aquarium {number}
- `ui/components/project_views/reports_tree_manager.py:313` — 🗑️ Delete Aquarium (drawing + data)...
- `ui/components/project_views/reports_tree_manager.py:317` — 🐟 Delete Animal (keep aquarium)...
- `ui/components/project_views/reports_tree_manager.py:335` — Delete Aquarium
- `ui/components/project_views/reports_tree_manager.py:336` — Delete aquarium {number} along with its drawings and analysis data?
- `ui/components/project_views/reports_tree_manager.py:346` — Do you also want to delete this aquarium's generated files from disk? ⏎  ⏎ If you choose 'No', only the ref...
- `ui/components/project_views/reports_tree_manager.py:372` — Delete the animal bound to aquarium {number}, keeping the drawn aquarium?
- `ui/components/project_views/reports_tree_manager.py:382` — Do you also want to delete this aquarium's current trajectory and reports? ⏎  ⏎ If you choose 'No', only th...
- `ui/components/project_views/reports_tree_manager.py:419` — Delete only the trajectory and reports of aquarium {number}, keeping the arena and the ROIs?
- `ui/components/single_video_workflow.py:520` — No aquarium has been defined.
- `ui/components/single_video_workflow.py:525` — The aquarium's main area (polygon) has not been defined.
- `ui/components/zone_context_panel.py:321` — Aquarium model: {value}
- `ui/ui_coordinator.py:775` — Detecting aquarium: frame {frame}/{total}

### Coordinators (not owned by stage 3) (32)

- `coordinators/_single_video_mixin.py:108` — Aquarium {number} has no subject defined. Configure the aquariums before processing.
- `coordinators/_video_selection_mixin.py:173` — The main aquarium polygon has not been defined
- `coordinators/dialog_coordinator.py:203` — The main aquarium polygon has not been defined. ⏎  ⏎ The main arena is required for an accurate analysis. ⏎...
- `coordinators/dialog_coordinator.py:235` — Please: ⏎ 1. Use 'Detect Aquarium (Auto)' or ⏎ 2. Draw the main polygon manually ⏎ 3. Then come back to add...
- `coordinators/live_calibration_coordinator.py:915` — Aquarium Detected
- `coordinators/live_calibration_coordinator.py:916` — Aquarium detected successfully! ⏎  ⏎ You can adjust the vertices or add ROIs. ⏎ Click 'Finish' when you are...
- `coordinators/live_calibration_coordinator.py:945` — Could not detect the aquarium automatically. ⏎  ⏎ You will be taken to the zones tab to draw it manually.
- `coordinators/live_calibration_coordinator.py:997` — Draw the Aquarium
- `coordinators/live_calibration_coordinator.py:998` — Draw the aquarium polygon and ROIs (if needed). ⏎  ⏎ Click 'Finish' when you are ready.
- `coordinators/live_calibration_coordinator.py:1056` — The main aquarium polygon has not been defined. ⏎  ⏎ Defining the arena before starting the recording is re...
- `coordinators/live_calibration_coordinator.py:1077` — Please: ⏎ 1. Use the live camera to calibrate ⏎ 2. Use 'Detect Aquarium (Auto)' or ⏎ 3. Draw the main polyg...
- `coordinators/live_calibration_coordinator.py:1160` — Detecting the aquarium...
- `coordinators/live_calibration_coordinator.py:1554` — Could not detect the aquarium automatically. ⏎  ⏎ The captured image was loaded for manual drawing. ⏎ Pleas...
- `coordinators/model_diagnostics_coordinator.py:957` —   - [MASK WITHOUT BOX] Probable Aquarium, approx. BBox: [{x_min}, {y_min}, {x_max}, {y_max}], Area: {area},...
- `coordinators/model_diagnostics_coordinator.py:1002` —   Masks without a bounding box (possible aquariums):
- `coordinators/multi_aquarium_coordinator.py:495` — Aquarium not detected
- `coordinators/multi_aquarium_coordinator.py:496` — The model found no aquarium in the first frames of this video. Draw the arena by hand, or try again with a ...
- `coordinators/multi_aquarium_coordinator.py:521` — Aquariums not detected
- `coordinators/multi_aquarium_coordinator.py:522` — The model did not find the aquariums in the first frames of this video. Draw each arena by hand, or try aga...
- `coordinators/multi_aquarium_coordinator.py:553` — Aquarium not detected
- `coordinators/multi_aquarium_coordinator.py:554` — The model found no aquarium in this video. The arena shown is a generic placeholder covering most of the fr...
- `coordinators/multi_aquarium_coordinator.py:569` — Aquarium shape not preserved
- `coordinators/multi_aquarium_coordinator.py:570` — Segmentation was requested, but the model returned no usable mask for this video. The arena was approximate...
- `coordinators/report_generation_coordinator.py:735` — {name}: multi-aquarium data missing.
- `coordinators/report_generation_coordinator.py:761` — {name} ({count} aquariums)
- `coordinators/report_generation_coordinator.py:767` — {name}: no aquarium processed.
- `coordinators/report_generation_coordinator.py:775` — {name}: multi-aquarium error {error}
- `coordinators/sequential_processing_coordinator.py:167` — Processing aquarium {current}/{total}...
- `coordinators/sequential_processing_coordinator.py:541` — Sequential processing finished: {done}/{total} aquariums.
- `coordinators/ui_state_coordinator.py:548` — Error: the main processing area (aquarium) has not been defined. Please define it in the 'Zone Configuratio...
- `coordinators/video_processing_coordinator.py:1028` — Aquarium {number}
- `coordinators/video_processing_coordinator.py:1037` — Video '{video}' has aquariums with no subject defined: ⏎  ⏎ {aquariums} ⏎  ⏎ Configure the aquariums before...

### Core services / recording / detection (not owned by stage 3) (27)

- `core/detection/multi_aquarium_detector.py:1196` — Aquarium {number}
- `core/project/project_workflow_service.py:129` — The detection mode (det) for animals is only compatible with 1 animal per aquarium. ⏎ Current configuration...
- `core/recording/condition_runtime.py:279` — Aquarium {number}: {message}
- `core/recording/frame_processing_pipeline.py:854` — 🔍 Detecting aquarium... ({current}/{total})
- `core/recording/live_analysis_post_processor.py:809` — Session WITHOUT calibration: the aquarium dimensions were not available, so 1 pixel was treated as 1 cm. Ev...
- `core/recording/live_analysis_post_processor.py:1313` — Multi-aquarium detection failed: {error} ⏎  ⏎ The preview keeps running, but the detections of this session...
- `core/recording/live_camera_mode.py:131` — The system supports {count} aquariums simultaneously. Real-time processing enabled.
- `core/recording/live_camera_mode.py:166` — The system supports only {supported} of the {requested} aquariums requested for simultaneous processing.
- `core/recording/live_camera_mode.py:176` — Recommended: process only 1 aquarium in this session.
- `core/recording/live_camera_mode.py:183` — Process only 1 aquarium now (ignore the rest)
- `core/recording/live_camera_mode.py:202` — ⚠️ The system does not support {count} aquariums simultaneously.
- `core/recording/live_camera_mode.py:208` — Maximum supported: 1 aquarium.
- `core/recording/live_camera_mode.py:210` — Maximum supported: {count} aquariums.
- `core/recording/live_session_manager.py:867` — 🔍 Looking for the aquarium...
- `core/services/wizard_service.py:761` — The number of aquariums must be between 1 and 100
- `core/services/wizard_service.py:768` — The number of animals per aquarium must be between 1 and 100
- `core/services/wizard_service.py:774` — The aquarium width must be greater than zero
- `core/services/wizard_service.py:778` — The aquarium height must be greater than zero
- `core/services/wizard_service.py:832` — The number of aquariums must be at least 1
- `core/services/wizard_service.py:835` — The number of aquariums cannot exceed 100
- `core/services/wizard_service.py:842` — The number of animals per aquarium must be at least 1
- `core/services/wizard_service.py:848` — The number of animals per aquarium cannot exceed 100
- `core/services/wizard_service.py:860` — The aquarium width cannot be negative (use 0 for no calibration)
- `core/services/wizard_service.py:861` — The aquarium width cannot exceed {maximum:g} cm
- `core/services/wizard_service.py:865` — The aquarium height cannot be negative (use 0 for no calibration)
- `core/services/wizard_service.py:866` — The aquarium height cannot exceed {maximum:g} cm
- `core/viewmodels/analysis_control_view_model.py:96` — The detection mode (det) for animals is only compatible with 1 animal per aquarium. ⏎ Current configuration...

### Analysis (warnings shown to the user) (2)

- `analysis/analysis_service.py:717` — The {protocol} protocol analyses one arena per video; its metrics are not computed for aquarium {aquarium} ...
- `analysis/reporters/barnes_section.py:131` — Multi-aquarium videos are analysed one arena at a time; the Barnes metrics were not computed.

### Utilities (5)

- `utils/hardware_capability.py:378` — System limited to 1 aquarium at a time in real time. For multiple aquariums, consider offline recording.
- `utils/hardware_capability.py:385` — Limited CPU ({cores} cores). Upgrading to 4+ cores improves multi-aquarium performance.
- `utils/hardware_capability.py:399` — System supports up to 2 aquariums simultaneously.
- `utils/hardware_capability.py:407` — System supports 2-3 aquariums simultaneously with good performance.
- `utils/hardware_capability.py:412` — Excellent system! Supports 4+ aquariums simultaneously at high performance.

## Gates run for this stage

See the final report of the `animal-terms` session (pytest fast/GUI/i18n, ruff, mypy, mutation
check, e2e flows, golden and legacy 7.2 tests).
