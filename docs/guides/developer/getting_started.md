# Developer Getting Started

This guide serves as the primary entry point for developers working on ZebTrack-AI.

> **Quick Links**
>
> - [Contributing Guide](../../../CONTRIBUTING.md) - Environment setup, coding style, and testing.
> - [Architecture Explanation](../../explanation/architecture.md) - Detailed system design and diagrams.
> - [Event Contracts Reference](../../reference/events.md) - Registry of all system events.
> - [Quick Reference](../../reference/QUICK_REFERENCE.md) - One-liners and critical summaries.

---

## 1. Architecture (Event-Driven)

ZebTrack-AI uses a decoupled **Event-Driven Architecture (EDA)**. Components (Views, Services) communicate via events rather than direct method calls, coordinated by Mediators.

### Key Changes

1. **Decoupling**: Components (e.g., `DialogManager`, `ZoneControlBuilder`) no longer call `ApplicationGUI` methods directly.
2. **Event Bus**: Communication happens via `EventBusV2`. A component publishes an event, and interested parties subscribe to it.
3. **Coordination**: Complex workflows are managed by `UICoordinator` (Mediator pattern), rather than the main controller managing everything.

---

## 2. Core Components

### EventBusV2

- **Location**: `src/zebtrack/ui/event_bus_v2.py`
- **Role**: A thread-safe, synchronous event bus.
- **Usage**:
  - **Publish**: `event_bus.publish(Event(UIEvents.MY_EVENT, data={...}))`
  - **Subscribe**: `event_bus.subscribe(UIEvents.MY_EVENT, self.handler)`
- **Synchronous Nature**: Handlers run immediately on the calling thread. If you publish from a background thread, the handler runs on that background thread.

### UICoordinator

- **Role**: The implementation of the **Mediator Pattern**.
- **Responsibility**: It subscribes to UI events and coordinates the response across multiple components.
- **Example**: When `ZONES_UPDATED` is published:
  1. `UICoordinator` receives the event.
  2. It tells `CanvasManager` to redraw.
  3. It tells `ValidationManager` to re-validate.
  4. It tells `ProjectViewManager` to refresh the summary.

---

## 3. Design Patterns

### Mediator Pattern

We use the Mediator pattern (`UICoordinator`) to prevent a "mesh" of dependencies where every component knows about every other component.

- **Anti-Pattern**: `DialogManager` calls `CanvasManager` directly.
- **Mediator Pattern**: `DialogManager` publishes event -> `UICoordinator` calls `CanvasManager`.

### Dual Mode (Transitional)

During migration, components support both legacy (direct call) and new (event) paths. See [Migration Guide](../docs/MIGRATION_GUIDE_V4.md) for details.

---

## 4. Best Practices

### Event Usage Guidelines

1. **Use `UIEvents` Enum**: Always use the typed enum `UIEvents`, never string literals.
2. **Keep Handlers Fast**: Since events are synchronous, slow handlers block the UI. Offload heavy processing to threads.
3. **Thread Safety**:
   - If your handler updates the GUI (Tkinter), you **must** ensure it runs on the Main Thread.
   - Use `root.after(0, callback)` if the event might come from a background thread (e.g., `PROCESSING_STATS_UPDATED`).
4. **Payload Documentation**: Document the `data` dictionary keys in `docs/EVENT_MAPPING.md`.

### Testing

- **Mocking**: Mock `EventBusV2` in unit tests. Verify `publish` was called with the expected event and payload.
- **Integration**: Use `tests/integration/` to test the full flow (Publish -> EventBus -> Subscriber).

### Code Style

- Follow the standards in [CONTRIBUTING.md](../CONTRIBUTING.md).
- Run `poetry run ruff check .` before committing.
