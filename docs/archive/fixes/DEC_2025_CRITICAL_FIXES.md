# December 2025 Critical Fixes Archive

This document archives historical bug fixes from December 2025 that were previously in `GEMINI.md`.
These are kept for reference but are no longer needed in the active AI context.

---

## 1. Multi-Aquarium Data Flow

- **Zone Serialization**: `ProcessingCoordinator` correctly detects `MultiAquariumZoneData` and
  serializes using `ZoneManager.multi_aquarium_zone_data_to_dict`.
- **Worker Deserialization**: `ProcessingWorker` deserializes using
  `ZoneManager.multi_aquarium_zone_data_from_dict`.
- **Partitioned Processing**: Worker switches to `detector.detect_partitioned_optimized()` and
  `recorder.write_partitioned_detection_data()` when multi-aquarium data is detected.

## 2. Video Validation & Persistence

- **Parquet Compatibility**: `ProjectManager.save_multi_aquarium_zone_data` exports Aquarium 0 zones
  to standard parquet for `VideoValidationService` compatibility.
- **Atomic Saving**: `save_project()` called after updating `parquet_files` map.

## 3. UI & Events

- **Zone Selection**: `EventDispatcher` subscribes to `ZONE_AQUARIUM_SELECTED`.
- **Listbox Update**: `update_zone_listbox` handles `MultiAquariumZoneData`.
- **Rendering**: `CanvasRenderer` supports `MultiAquariumZoneData` natively.
- **Trajectory Generation**: Added `PROCESSING_GENERATE_TRAJECTORIES` handler.

## 4. Windows Taskbar Icon

- Added `AppUserModelID` setup in `__main__.py`.

## 5. Infinite Loop & Crash Fixes

- Removed redundant `ZONE_AUTO_DETECT` subscription in `MainViewModel`.
- Fixed `AttributeError` for `MultiAquariumZoneData.polygon` access.
- Fixed `ZoneManager.save_zone_data` routing for multi-aquarium data.

## 6. Multi-Aquarium Detector Logic Fixes

- Fixed empty `self._aquariums` in `Detector.set_zones`.
- Fixed `KeyError: 0` in `self._byte_trackers_multi`.
- Fixed `BYTETracker` initialization to use `SimpleNamespace`.

## 7. Multi-Aquarium Reporting + Reports UI

- Report generation uses `get_multi_aquarium_zone_data()` (not `get_zone_data()`).
- Re-register `multi_aquarium_outputs` after artifact generation.
- Normalize keys (`0` vs `"0"`) for Treeview iid.

## 8. Interval Persistence & UI Help

- Added `display_interval` to `VideoProcessingSettings`.
- Default intervals set to 5 frames.
- Default `aquarium_perspective` changed to LATERAL.

## 9. Simultaneous Multi-Aquarium Reports

- Fixed `is_multi_aquarium` reset logic in `on_video_completed`.
- Detect `aquarium_0`/`aquarium_1` folders on disk.

## 10. EventBus & Initialization Stability

- Suppressed false "no handlers" warnings.
- Fixed `BehavioralConfigWidget` to use `publish_event()`.

## 11. Single Video Analysis & Geotaxis Enhancements

- Fixed perspective persistence from UI to pipeline.
- Reports use descriptive zone headers ("Fundo", "Meio", "Superfície").
- Added horizontal zone boundary lines on plots.
