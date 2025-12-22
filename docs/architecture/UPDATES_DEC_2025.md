# Architectural Updates - December 2025

**Status:** Implemented
**Date:** Dec 12, 2025
**Scope:** Zone Management, Data Persistence, UI/UX Improvements

---

## 1. Zone Data Persistence Strategy (Hybrid Memory/Disk)

**Problem:** Previously, the application suffered from a "Split Brain" issue where:
- The **Analysis/Validation** system looked for Parquet files on disk.
- The **Zone Editor (UI)** looked for Zone Data in the in-memory Project JSON.
- This caused issues when reopening projects or copying zones, as the files existed but the editor thought the video was empty.

**Solution:** Implemented a robust **Hybrid Persistence Strategy**:

1.  **Eager Parquet Export:**
    - Whenever zones are saved (`ProjectManager.save_zone_data`), the system now **automatically exports** them to Parquet files (`1_ProcessingArea...`, `2_AreasOfInterest...`) in the correct project structure (`Project/Group/Day/Subject/`).
    - This ensures that the "Analysis view" of the data is always up-to-date with the "Editor view".

2.  **Lazy Load from Disk (Self-Healing):**
    - When a video is selected (`ProjectManager.set_active_zone_video`), the system checks if in-memory data is missing.
    - If missing, it aggressively scans the expected project directory for Parquet files.
    - If files are found, they are **loaded into memory immediately**, syncing the editor state with the disk state.

3.  **Smart Copy/Paste:**
    - The "Copy Zones" feature now looks up source files in the project registry if they are not found next to the video file, allowing cross-video copying even when videos are stored externally.

---

## 2. New Events

### `ZONE_CONCLUDE_VIDEO`
**Purpose:** Explicitly signal that the user has finished editing zones for a video.
**Trigger:** User clicks the "✅ Concluir" button in Zone Controls.
**Handler:** `ZoneControlBuilder._on_conclude_video` (via `EventDispatcher`).
**Actions:**
1.  Saves the project (persisting `has_arena`/`has_rois` flags).
2.  Refreshes the video tree to update status indicators immediately.

---

## 3. UI/UX Improvements

### Zone Controls
- **"Conclude" Button:** Added a dedicated button to finalize editing, positioned next to the ROI button.
- **Column Resizing:** The Zone List columns ("Nome", "Tipo", "Cor") now resize proportionally (60%/20%/20%) to better utilize space.

### Processing Reports
- **Selection Logic:** Updated to correctly count selected videos even if they have report files attached (treating them as "folders" in the tree view).

### Wizard
- **Model Selection:** Improved layout of the "Guia Rápido" to prevent text truncation.

---

## 4. Deprecations & Removals

- **Legacy Pipeline Table:** The code related to the old "Pipeline" tab (`refresh_pipeline_video_table`) has been removed as it was dead code and generating warning logs.
- **`PROJECT_CREATED` Event:** Removed the emission of this unused event to clear log warnings.

---

## 5. Sequential Multi-Aquarium Processing (v3.1)

**Date:** Dec 21, 2025

### Problem
Multi-aquarium processing always ran in parallel mode (both aquariums processed simultaneously in 1 video pass). Some users wanted the option to process each aquarium separately for:
- Better resource utilization per aquarium
- Lower memory usage (only 1 ByteTracker active at a time)
- Easier debugging (1 processing flow at a time)

### Solution

Implemented **Sequential Processing Mode** with toggle in Zone Controls:

1. **New Data Field**: `MultiAquariumZoneData.sequential_processing: bool`
   - `False` (default): Parallel mode - 1 video pass
   - `True`: Sequential mode - 2 video passes

2. **New Event**: `ZONE_PROCESSING_MODE_CHANGED`
   - Payload: `{sequential: bool}`
   - Emitted by ZoneControls radio buttons

3. **New Methods** (in `ProcessingCoordinator`):
   - `_start_sequential_multi_aquarium_processing()` - Initializes context, starts first aquarium
   - `_process_next_aquarium_in_sequence()` - Advances to next aquarium or finalizes
   - `_start_single_aquarium_for_sequential()` - Runs single-aquarium flow for each

4. **Report Generation**: After all aquariums complete:
   - Calls `register_multi_aquarium_outputs()` with collected outputs
   - Calls `generate_project_reports()` to generate Word/Excel/Parquet summaries

### Data Flow (Sequential Mode)
```
Passagem 1 ──► AquariumData[0].to_zone_data() ──► detect() ──► aquarium_0/
                                                              ↓ (automático)
Passagem 2 ──► AquariumData[1].to_zone_data() ──► detect() ──► aquarium_1/
                                                              ↓
Finalização ──► register_multi_aquarium_outputs() ──► generate_project_reports()
```

### Files Modified
- `src/zebtrack/ui/events.py` - New event `ZONE_PROCESSING_MODE_CHANGED`
- `src/zebtrack/core/detector.py` - New field `sequential_processing`
- `src/zebtrack/core/zone_manager.py` - Updated serialization
- `src/zebtrack/ui/components/zone_controls.py` - UI toggle (radio buttons)
- `src/zebtrack/ui/components/canvas_manager.py` - `update_processing_mode()` method
- `src/zebtrack/ui/components/event_dispatcher.py` - Event subscription
- `src/zebtrack/coordinators/processing_coordinator.py` - Sequential processing logic

### Output Structure (identical to parallel mode)
```
video_results/
├── aquarium_0/
│   ├── 3_CoordMovimento_{video}.parquet
│   ├── 4_Relatorio_{video}_aq0.docx
│   ├── 4_Relatorio_{video}_aq0.xlsx
│   └── {video}_aq0_summary.parquet
└── aquarium_1/
    ├── 3_CoordMovimento_{video}.parquet
    ├── 4_Relatorio_{video}_aq1.docx
    ├── 4_Relatorio_{video}_aq1.xlsx
    └── {video}_aq1_summary.parquet
```

### Trade-offs
| Aspect | Parallel | Sequential |
|--------|----------|------------|
| Speed | 1× (faster) | 2× (slower) |
| Memory | Higher (2 trackers) | Lower (1 tracker) |
| Resources | Split between aquariums | 100% per aquarium |
| Debugging | More complex | Easier |
| Code Path | Multi-aquarium specific | Reuses single-aquarium |
