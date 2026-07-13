# Operational Reference & API Stability

**Category:** Reference (Diátaxis)
**Status:** Canonical
**Last Updated:** February 2, 2026

This document defines the stable public interfaces of the DRerio LogAI core services. Developers should rely on these methods when extending the system or integrating with new UI components.

## 1. Core Services API

### 1.1. DetectorService

**Location:** `src/zebtrack/core/detector_service.py`

| Method                       | Signature                                                             | Description                                      |
| ---------------------------- | --------------------------------------------------------------------- | ------------------------------------------------ |
| `initialize_detector`        | `(animal_method, use_openvino, active_weight_name, detector_plugins)` | Loads a YOLO or OpenVINO model.                  |
| `configure_zones`            | `(zone_data, width, height)`                                          | Internal scaling and multi-aquarium setup.       |
| `update_tracking_parameters` | `(params, reset_overrides, ...)`                                      | Updates thresholds (Confidence, NMS, ByteTrack). |
| `reset_tracking_state`       | `()`                                                                  | Clears Kalman filters and track history.         |

### 1.2. StateManager

**Location:** `src/zebtrack/core/state_manager.py`

| Method                   | Signature              | Description                                |
| ------------------------ | ---------------------- | ------------------------------------------ |
| `update_project_state`   | `(source, **kwargs)`   | Atomic update of project metadata.         |
| `update_recording_state` | `(source, **kwargs)`   | Atomic update of session flags and params. |
| `subscribe`              | `(category, observer)` | Register a callback for state changes.     |

### 1.3. ProjectManager

**Location:** `src/zebtrack/core/project_manager.py`

| Method                            | Signature                            | Description                                |
| --------------------------------- | ------------------------------------ | ------------------------------------------ |
| `save_project`                    | `()`                                 | Persists the `config.yaml` to disk.        |
| `get_multi_aquarium_zone_data`    | `(video_path)`                       | Resolves dual-tank geometries for a video. |
| `register_multi_aquarium_outputs` | `(video_path, aquarium_id, outputs)` | Persists analysis result paths.            |

---

## 2. Super Coordinator Contracts

The system is orchestrated by four "Super Coordinators" that mediate between UI events and core services.

### 2.1. ProcessingCoordinator

**Location:** `src/zebtrack/coordinators/processing_coordinator.py`

- Handles video processing loops, analysis pipelines, and progress reporting.
- **Key Event:** `Events.VIDEO_ANALYZE_SINGLE`

### 2.2. HardwareCoordinator

**Location:** `src/zebtrack/coordinators/hardware_coordinator.py`

- Manages model weights, detector initialization, and diagnostic tests.
- **Key Event:** `Events.MODEL_SET_WEIGHT`

### 2.3. SessionCoordinator

**Location:** `src/zebtrack/coordinators/session_coordinator.py`

- Directs recording sessions and live camera analysis.
- **Key Event:** `RECORDING_START`, `RECORDING_STOP`

### 2.4. ProjectLifecycleCoordinator

**Location:** `src/zebtrack/coordinators/project_lifecycle_coordinator.py`

- Coordinates project creation, opening, and asset validation.
- **Key Event:** `PROJECT_CREATE`, `PROJECT_OPEN`

---

## 3. UI API Stability (View Layer)

While the View layer is technically flexible, the `ApplicationGUI` class provides a stable façade for common UI tasks:

| Method                       | Description                                |
| ---------------------------- | ------------------------------------------ |
| `show_error(title, message)` | Displays a modal error dialog.             |
| `set_status(text)`           | Updates the bottom status bar.             |
| `update_progress(value)`     | Moves the global progress bar (0-100).     |
| `root.after(0, callback)`    | **MANDATORY** for cross-thread UI updates. |

---

## 4. Change Policy

1. **Semantic Versioning:** Breaking changes to these methods require a major version bump (e.g., v4.1 -> v5.0).
2. **Event over Method:** Prefer publishing a UI Event in `EventBusV2` over calling a method on a coordinator directly.
3. **Strict DI:** Do not use singleton imports for settings; always use the injected `settings_obj`.
