# ZebTrack-AI Architecture Overview (v4.0+)

**Status:** Canonical Reference
**Last Updated:** February 2, 2026
**Category:** Explanation (Diátaxis)

## 1. Core Philosophy: Event-Driven & Decoupled

ZebTrack-AI has evolved from a monolithic "God Object" architecture (v3.0) to a modular **Event-Driven Architecture (EDA)** utilizing the **Mediator** and **Dependency Injection** patterns. This ensures scalability, testability, and a clear separation of concerns between the User Interface (View) and the Business Logic (ViewModel/Model).

### 1.1. The Transition
- **v3.0 (Legacy):** `ApplicationGUI` coordinated all workflows. Components were tightly coupled, leading to circular dependencies and difficult maintenance.
- **v4.1 (Current):** Components are independent agents. They communicate primarily via a central `EventBusV2` or domain-specific `EventBus`. A `UICoordinator` acts as a Mediator to handle complex UI orchestrations.

## 2. Component Synergy

The system is organized into three distinct layers:

### 2.1. View Layer (Tkinter)
- **Managers:** Specialized components (e.g., `CanvasManager`, `DialogManager`) that handle specific UI regions.
- **Widgets:** Reusable Tkinter components under `zebtrack.ui.widgets`.
- **Constraint:** Views must **NEVER** contain business logic or directly call backend services. They publish events or call injected viewmodel methods.

### 2.2. Coordination Layer (Mediators)
- **UICoordinator:** Listens to `UIEvents` and coordinates responses across multiple Managers.
- **Super Coordinators (Backend):** Four specific services that manage complex domain logic:
  - **ProcessingCoordinator:** Video loops, analysis, and `ProcessingWorker` lifecycle.
  - **HardwareCoordinator:** Detector parameters, model weights, and camera diagnostics.
  - **SessionCoordinator:** Recording sessions, Arduino triggers, and live analysis.
  - **ProjectLifecycleCoordinator:** Project CRUD, calibration, and zone persistence.

### 2.3. Logic Layer (Coordinators & Services)
- **DetectorService:** Wraps plugins (YOLO/OpenVINO) and handles zone scaling.
- **ProjectManager:** Handles data persistence and project structure.
- **Recorder:** Manages Parquet and MP4 output.

## 3. Communication Patterns

### 3.1. Synchronous: Dependency Injection (DI)
All services receive their dependencies via constructor injection. Singleton imports (e.g., `from zebtrack import settings`) are strictly forbidden. Use `settings_obj: Settings` parameter instead.

### 3.2. Asynchronous/Decoupled: Event Bus
The system uses a Dual Event Bus architecture:
- **EventBus (v1):** String constants for domain-level events (Recording, Analysis).
- **EventBusV2:** Enum constants for UI-level events (Zones, Refresh, Selection).

## 4. Multi-Aquarium Logic

The system supports tracking two subjects simultaneously in separate aquariums within the same video frame.

- **Detection:** Uses contour analysis to identify tank boundaries (Zones).
- **Track Separation:** Global track IDs use the formula `aquarium_id * 1000 + local_id`.
  - Aquarium 0 (Left): IDs 1-999.
  - Aquarium 1 (Right): IDs 1001-1999.
- **Data Isolation:** Each aquarium has its own `ByteTracker` instance and generates its own output reports in the experimental hierarchy.

## 5. Life of an Event: "Zones Updated"
1. **Action:** User edits a zone in `DialogManager`.
2. **Publish:** `DialogManager` publishes `UIEvents.ZONES_UPDATED`.
3. **Dispatch:** `EventBusV2` notifies all subscribers.
4. **Mediation:** `UICoordinator` receives the event and:
   - Tells `CanvasManager` to redraw.
   - Tells `ProjectViewManager` to refresh visibility.
   - Tells `ValidationManager` to re-check video readiness.

## 5. Directory Structure Mapping

- `src/zebtrack/core/`: Backend Coordinators and Logic.
- `src/zebtrack/ui/`: UI Bootstrapping, Coordinators, and Event Buses.
- `src/zebtrack/ui/components/`: View Managers.
- `src/zebtrack/ui/widgets/`: Reusable GUI elements.
- `src/zebtrack/io/`: Data I/O (VideoSource, Recorder, Serial).
- `src/zebtrack/analysis/`: Behavioral algorithms and Reporting.

---
**Scientific Verification:** This architecture ensures deterministic data flow, where tracking results are separated from visualization artifacts, facilitating audit trails and reproducibility.
