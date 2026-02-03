# Event Mapping - Component → GUI Communication

**Version**: 4.0 (Draft)
**Related Plan**: PLANO_ACAO_V4.md (Track 2)

This document maps legacy Component→GUI direct calls (v3) to the new Event Bus V2 events (v4).
It specifically addresses the "11 Component -> GUI calls" identified in the architectural analysis.

---

## 1. ZONES_UPDATED
**Replaces**: `gui.update_zone_listbox(zone_data)`
**Legacy Callers (5)**:
- `DialogManager`
- `PolygonDrawingService`
- `ROITemplateManager`
- `ZoneControlBuilder`
- `Renderer`
**Subscriber**: `CanvasManager` (via `UICoordinator` or direct subscription)
**Payload**:
```python
{
    "zone_data": ZoneData | None  # The updated zone data object, or None to clear
}
```
**Priority**: CRITICAL (High impact on UI consistency)

---

## 2. VIDEO_TREE_REFRESH_REQUESTED
**Replaces**: `gui._populate_video_selector_tree(filter_text)`
**Legacy Callers (3)**:
- `ZoneControlBuilder` (called twice in different contexts)
- `ProjectViewManager`
**Subscriber**: `ProjectViewManager`
**Payload**:
```python
{
    "filter_text": str | None  # Filter string for the video tree, or None
}
```
**Priority**: HIGH (Navigation consistency)

---

## 3. READINESS_SNAPSHOT_UPDATED
**Replaces**: `gui.apply_pending_readiness_snapshot(...)`
**Legacy Caller (1)**:
- `DialogManager` (after zone reuse dialog)
**Subscriber**: `ProjectViewManager` / `ValidationManager`
**Payload**:
```python
{
    "ready_with_trajectory": int,
    "ready_with_zones": int,
    "arena_only": int,
    "without_arena": int
    # ... other snapshot fields
}
```
**Priority**: MEDIUM

---

## 4. POLYGON_EDIT_REQUESTED
**Replaces**: `gui.setup_interactive_polygon(polygon)`
**Legacy Caller (1)**:
- `CanvasManager` (initiates editing)
**Subscriber**: `CanvasManager` (or `DrawingStateManager`)
**Payload**:
```python
{
    "polygon": np.ndarray  # The polygon points to edit
}
```
**Priority**: MEDIUM

---

## 5. VIDEO_HIERARCHY_SNAPSHOT_REQUESTED
**Replaces**: `gui._build_video_hierarchy_snapshot()`
**Legacy Caller (1)**:
- `ProjectViewManager`
**Subscriber**: `ProjectViewManager` (Self-contained update)
**Payload**:
```python
{
    # Empty payload or optional context
}
```
**Priority**: LOW (Internal state refresh)

---

## 6. ZONE_COPY_ZONES (New - Dec 2025)
**Purpose**: Copy zones from a video to clipboard
**Publishers (1)**:
- `ZoneControls` (context menu)
**Subscriber**: `EventDispatcher` -> `CanvasManager.copy_zones_from_video()`
**Payload**:
```python
{
    "video_path": str  # Path to the video to copy zones from
}
```
**Priority**: MEDIUM (Zone management)

---

## 7. ZONE_PASTE_ZONES (New - Dec 2025)
**Purpose**: Paste zones from clipboard to a video
**Publishers (1)**:
- `ZoneControls` (context menu)
**Subscriber**: `EventDispatcher` -> `CanvasManager.paste_zones_to_video()`
**Payload**:
```python
{
    "video_path": str  # Path to the video to paste zones to
}
```
**Priority**: MEDIUM (Zone management)

---

## 8. ZONE_DELETE_ZONES (New - Dec 2025)
**Purpose**: Delete all zones from a video
**Publishers (1)**:
- `ZoneControls` (context menu)
**Subscriber**: `EventDispatcher` -> `CanvasManager.delete_zones_from_video()`
**Payload**:
```python
{
    "video_path": str  # Path to the video to delete zones from
}
```
**Priority**: MEDIUM (Zone management)

---

## 9. ZONE_FINISH_DRAWING (New - Dec 2025)
**Purpose**: Complete polygon drawing (alternative to double-click)
**Publishers (1)**:
- `ZoneControls` (button click)
**Subscriber**: `EventDispatcher` -> `CanvasManager.finish_current_polygon()`
**Payload**:
```python
{
    # Empty payload
}
```
**Priority**: LOW (Drawing UX improvement)

---

---

## 10. ZONE_PROCESSING_MODE_CHANGED (New - Dec 2025)
**Purpose**: Toggle between parallel and sequential multi-aquarium processing
**Publishers (1)**:
- `ZoneControls` (radio button selection)
**Subscriber**: `EventDispatcher` -> `CanvasManager.update_processing_mode()`
**Payload**:
```python
{
    "sequential": bool  # True = 2 passes (sequential), False = 1 pass (parallel)
}
```
**Priority**: MEDIUM (Multi-aquarium workflow)

---

## Summary of Changes

| Current Method | New Event | Callers | Status |
|---|---|---|---|
| `update_zone_listbox` | `ZONES_UPDATED` | 5 | ✅ Defined |
| `_populate_video_selector_tree` | `VIDEO_TREE_REFRESH_REQUESTED` | 3 | ✅ Defined |
| `apply_pending_readiness_snapshot` | `READINESS_SNAPSHOT_UPDATED` | 1 | ✅ Defined |
| `setup_interactive_polygon` | `POLYGON_EDIT_REQUESTED` | 1 | ✅ Defined |
| `_build_video_hierarchy_snapshot` | `VIDEO_HIERARCHY_SNAPSHOT_REQUESTED` | 1 | ✅ Defined |
| (new) `copy_zones_from_video` | `ZONE_COPY_ZONES` | 1 | ✅ New Dec 2025 |
| (new) `paste_zones_to_video` | `ZONE_PASTE_ZONES` | 1 | ✅ New Dec 2025 |
| (new) `delete_zones_from_video` | `ZONE_DELETE_ZONES` | 1 | ✅ New Dec 2025 |
| (new) `finish_current_polygon` | `ZONE_FINISH_DRAWING` | 1 | ✅ New Dec 2025 |
| (new) `update_processing_mode` | `ZONE_PROCESSING_MODE_CHANGED` | 1 | ✅ New Dec 2025 |

**Total Mapped Calls**: 16

