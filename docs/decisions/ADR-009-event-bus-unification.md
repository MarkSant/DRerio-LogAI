# ADR-009: EventBus Unification — EventBusV2 as Canonical Bus

**Status**: Accepted
**Decision Date**: February 15, 2026
**Phase**: 3.7 (Refactoring Roadmap)
**Deprecation Start**: v4.1 (February 2026)
**Removal Target**: v5.0

## Problem

Two EventBus implementations coexist with no documented plan for convergence:

| Dimension | EventBus v1 (`event_bus.py`) | EventBusV2 (`event_bus_v2.py`) |
|---|---|---|
| **LOC** | 273 | 216 |
| **Event identifiers** | Plain strings (`"recording:start"`) | Enum members (`UIEvents.ZONES_UPDATED`) |
| **Dispatch model** | Async: queue → `drain()` → `dispatch_named_event()` on UI thread | Synchronous: direct dispatch on calling thread |
| **Thread safety** | Queue is thread-safe; `_subscribers` dict is **not** locked | `threading.RLock` protects subscriber state |
| **Monitoring** | None | 100ms slow-handler logging |
| **Event catalog** | `Events` class: ~97 string constants (`events.py`) | `UIEvents` enum: 37 members (inline) |
| **Consumer files** | ~33 files (coordinators, core, UI widgets) | ~12 files (UI components: canvas, dialog, menu, tab) |
| **Instance creation** | `__main__.py` (Composition Root) | `gui.py` (MainWindow) |

Three files import **both** buses: `gui.py`, `ui_coordinator.py`,
`video_processing_service.py`.

A new developer cannot determine which bus to use. There is no deprecation
plan, no ADR, and no timeline for convergence. The audit report
(February 2026) flagged this as a structural deficiency.

## Decision

**EventBusV2 is the canonical event bus.** EventBus v1 is deprecated
starting v4.1 (February 2026) with removal target v5.0.

### Rationale

1. **Type safety**: Enum-based event identifiers (`UIEvents.X`) provide
   compile-time discovery, autocomplete, and prevent typo-based bugs.
   String-based identifiers (`"recording:start"`) are error-prone and
   require manual cross-referencing with the `Events` catalog class.

2. **Thread safety**: v2 uses `threading.RLock` on `_subscribers`,
   preventing race conditions during concurrent subscribe/unsubscribe.
   v1's `_subscribers` (a `defaultdict(list)`) has no lock protection.

3. **Performance monitoring**: v2 logs handlers exceeding 100ms as
   tech debt. v1 has no handler performance visibility.

4. **Simpler dispatch**: v2's synchronous dispatch eliminates the
   queue-drain-dispatch indirection. Callers that need UI-thread
   scheduling can use `root.after()` directly, which is already the
   pattern in all coordinators.

5. **Alignment with v4 EDA**: v2 was designed as the foundation for
   the v4 Event-Driven Architecture. Converging on v2 aligns with
   the architectural roadmap.

## Migration Plan

### Phase 3.7 (This Phase — February 2026)

- Add `DeprecationWarning` to EventBus v1's `publish_event()`,
  `subscribe()`, and `publish_callable()` methods
- Create this ADR documenting the decision
- Add pytest.ini filter to suppress expected warnings in test output
- **No consumer migration** — all 33+ files continue using v1 unchanged

### Phase 4+ (Future — During Coordinator Decomposition)

When coordinators are decomposed (e.g., `ProcessingCoordinator` split
into smaller units), each refactored coordinator will be migrated from
v1 to v2 as a natural part of the refactoring:

1. **Map `Events` string constants → `UIEvents` enum members**.
   Example: `Events.RECORDING_START` (`"recording:start"`) →
   `UIEvents.RECORDING_START` (new enum member to add).

2. **Replace `event_bus.publish_event(Events.X, data)` calls** with
   `event_bus_v2.publish(Event(UIEvents.X, data))`.

3. **Replace `event_bus.subscribe(Events.X, handler)` calls** with
   `event_bus_v2.subscribe(UIEvents.X, handler)`.

4. **Migrate `publish_callable()` calls** — replace with either
   `root.after(0, callback)` (for UI-thread scheduling) or
   `EventBusV2.publish()` (for event-driven communication).

5. **Consolidate event catalogs** — progressively move `Events`
   string constants into `UIEvents` enum members until the `Events`
   class is empty.

### Phase 5 / v5.0 (Removal)

- Delete `event_bus.py` (v1)
- Delete `Events` class from `events.py` (string constants)
- Remove pytest.ini suppression filter
- Remove `DeprecationWarning` references from documentation

## Consequences

### Immediate

- v1 consumers see `DeprecationWarning` during development and testing.
  Python's default filter shows each unique call site once per process,
  preventing log flooding.
- No production user impact: Python hides `DeprecationWarning` from
  non-`__main__` modules by default.
- Test output won't be cluttered: pytest.ini filter suppresses the
  expected warnings.
- New contributors know which bus to use (v2) via this ADR and the
  deprecation warning message.

### Future

- Migration effort is ~33 files but can be done incrementally alongside
  coordinator decomposition (Phase 4).
- Once complete, the project will have a single, type-safe, thread-safe
  event bus with performance monitoring.
- The `Events` string catalog (~97 constants) will be absorbed into
  `UIEvents` enum (~37 members currently → ~134 after full migration).

## Alternatives Considered

1. **Keep v1, deprecate v2** — Lower migration effort (12 files vs 33),
   but sacrifices type safety, thread safety, and monitoring.
   Rejected: v2 is architecturally superior.

2. **Merge both into a new v3** — Clean-slate design. Rejected: v2
   already has the right design; a v3 would be v2 with minor renaming.
   Not worth the churn.

3. **Keep both indefinitely** — Status quo. Rejected: the coexistence
   causes confusion and was flagged by the technical audit as a
   structural deficiency.

## References

- EventBus v1: `src/zebtrack/ui/event_bus.py` (273 LOC)
- EventBusV2: `src/zebtrack/ui/event_bus_v2.py` (216 LOC)
- Events catalog: `src/zebtrack/ui/events.py` (~97 string constants)
- Technical audit: `docs/Relatorio Opus 6 Melhoris.txt` (Section 1,
  "Dois EventBus coexistindo")
- Existing deprecation pattern: `src/zebtrack/analysis/reporter.py`
  (lines 210-223)

## Change Log

- **2026-02-15**: ADR created during Phase 3.7. DeprecationWarning added
  to EventBus v1 `publish_event()`, `subscribe()`, `publish_callable()`.
- **2026-02-03**: Phase 8 update. Phase 4 coordinator decomposition
  completed (17 coordinators extracted), but v1 → v2 consumer migration
  has **not yet started**. Both buses still coexist. Migration will occur
  during the next refactoring cycle targeting Event-Driven Architecture
  convergence. Current state: v1 still has ~33 consumer files; v2 has
  ~12 consumer files. pytest.ini filter suppresses expected warnings.
