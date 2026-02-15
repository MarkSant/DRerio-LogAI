# ZebTrack-AI Event Contracts & Registry

**Status:** Canonical Reference
**Last Updated:** February 2, 2026
**Category:** Reference (Diátaxis)

This document defines the strict contracts for event-driven communication in ZebTrack-AI. All publishers and subscribers must adhere to these payloads.

---

## 1. Dual Event Bus Overview

ZebTrack-AI utilizes two coexisting event bus systems to separate domain logic from UI orchestration.

| System            | Enum/Class        | Primary Use Case                          |
| ----------------- | ----------------- | ----------------------------------------- |
| **EventBus (v1)** | `Events` (string) | Domain: Recording, Analysis, Project CRUD |
| **EventBusV2**    | `UIEvents` (enum) | UI: Component sync, Canvas, Selection     |

---

## 2. Domain Events (EventBus v1)

### 2.1. Video Analysis & Processing

| Event Name              | Payload Requirements                          | Description                                    |
| :---------------------- | :-------------------------------------------- | :--------------------------------------------- |
| `VIDEO_ANALYZE_SINGLE`  | `{video_path: str, config: dict}`             | Triggers processing of a single video.         |
| `VIDEO_CANCEL_ANALYSIS` | None                                          | Stop all active processing and worker threads. |
| `UI_DISPLAY_FRAME`      | `{frame: np.ndarray, detections: list (opt)}` | Send frame to Canvas (Worker only).            |
| `UI_SET_STATUS`         | `{message: str}`                              | Update the GUI status bar.                     |

### 2.2. Multi-Aquarium Events (v3.1+)

| Event Name                             | Payload Requirements                        | Description                               |
| :------------------------------------- | :------------------------------------------ | :---------------------------------------- |
| `ZONE_MULTI_AUTO_DETECT`               | `{video_path: str, expected_count: int}`    | Start automatic tank detection.           |
| `ZONE_AQUARIUM_SELECTED`               | `{aquarium_id: int}`                        | Switch active view context.               |
| `ZONE_AQUARIUM_CONFIG_UPDATED`         | `{aquarium_id: int, config: dict}`          | Persist changes to aquarium settings.     |
| `ZONE_SHOW_AQUARIUM_ASSIGNMENT_DIALOG` | `{video_path: str, available_groups: list}` | Trigger the group/subject mapping dialog. |

---

## 3. UI Events (EventBusV2)

### 3.1. Zone & Interaction

| Event Name                        | Payload Requirements                      | Description                              |
| --------------------------------- | ----------------------------------------- | ---------------------------------------- |
| `ZONES_UPDATED`                   | `{'zone_data': ZoneData \| None}`         | Zones (arena/ROIs) were altered.         |
| `POLYGON_EDIT_REQUESTED`          | `{'polygon': np.ndarray}`                 | Request to edit polygon vertices.        |
| `VIDEO_TREE_REFRESH_REQUESTED`    | `{'filter_text': str \| None}`            | Request to refresh video selector tree.  |
| `PROJECT_VIEWS_REFRESH_REQUESTED` | `{'reason': str, 'append_summary': bool}` | Generic request to update project views. |
| `READINESS_SNAPSHOT_UPDATED`      | `{'ready_with_trajectory': [...], ...}`   | Update video readiness status.           |
| `VIDEO_LOADED`                    | `{'video_path': str}`                     | Notification that a new video is loaded. |
| `EXTERNAL_TRIGGER_NOTICE`         | `{'session_label': str, ...}`             | Waiting for external trigger (Arduino).  |

### 3.2. Multi-Aquarium UI Events

| Event Name                       | Payload Requirements                             | Description                            |
| -------------------------------- | ------------------------------------------------ | -------------------------------------- |
| `ZONE_MULTI_AUTO_DETECT`         | `{'video_path': str}`                            | Trigger multi-aquarium auto-detection. |
| `ZONE_MULTI_AUTO_DETECT_SUCCESS` | `{'video_path': str, 'polygons': list}`          | Multi-aquarium detection success.      |
| `ZONE_MULTI_AUTO_DETECT_FAILED`  | `{'video_path': str, 'reason': str}`             | Multi-aquarium detection failure.      |
| `ZONE_AQUARIUM_SELECTED`         | `{'aquarium_id': int}`                           | Specific aquarium selected by user.    |
| `ZONE_MULTI_DETECT_COMPLETED`    | `{'count': int, 'aquariums': list}`              | Detection finished with count results. |
| `ZONE_AQUARIUM_CONFIG_CONFIRMED` | `{'configs': list[AquariumConfig]}`              | Aquarium configuration confirmed.      |
| `ZONE_AQUARIUM_CONFIG_UPDATED`   | `{'id': int, 'config': dict, 'video_path': str}` | Individual aquarium config updated.    |

---

## 4. How to Use (Implementation Patterns)

### 4.1. Publishing an Event (Publisher)

Use when an action occurs that other components need to know about.

```python
from zebtrack.ui.event_bus_v2 import Event, UIEvents

if self.event_bus_v2:
    self.event_bus_v2.publish(Event(
        type=UIEvents.ZONES_UPDATED,
        data={'zone_data': new_zone_data},
        source='MyComponent'
    ))
```

### 4.2. Subscribing to an Event (Subscriber)

Typically implemented in the `UICoordinator`.

```python
self.event_bus.subscribe(UIEvents.ZONES_UPDATED, self._on_zones_updated)

def _on_zones_updated(self, data: dict):
    zone_data = data.get('zone_data')
    # React to the data...
```

---

## 5. Track ID Convention

**Global ID = `aquarium_id * 1000 + local_track_id`**

- Aquarium 0: 0 - 999
- Aquarium 1: 1000 - 1999
- Aquarium 2: 2000 - 2999

---

## 5. Payloads & Types

### 5.1. ZoneData

Zones must be serialized using `ZoneManager.zone_data_to_dict()` before being sent across boundaries (e.g., to the `ProcessingWorker`).

### 5.2. Processing Stats

Published via `PROCESSING_STATS_UPDATED`:

```json
{
  "fps": 30.5,
  "frame": 500,
  "total_frames": 1800,
  "eta_seconds": 42
}
```
