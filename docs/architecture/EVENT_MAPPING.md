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

## Summary of Changes

| Current Method | New Event | Callers | Status |
|---|---|---|---|
| `update_zone_listbox` | `ZONES_UPDATED` | 5 | ✅ Defined |
| `_populate_video_selector_tree` | `VIDEO_TREE_REFRESH_REQUESTED` | 3 | ✅ Defined |
| `apply_pending_readiness_snapshot` | `READINESS_SNAPSHOT_UPDATED` | 1 | ✅ Defined |
| `setup_interactive_polygon` | `POLYGON_EDIT_REQUESTED` | 1 | ✅ Defined |
| `_build_video_hierarchy_snapshot` | `VIDEO_HIERARCHY_SNAPSHOT_REQUESTED` | 1 | ✅ Defined |

**Total Mapped Calls**: 11
