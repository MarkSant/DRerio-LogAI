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
