# Impact Analysis Protocol for Code Changes

**Status:** Mandatory for All Agents
**Last Updated:** Jan 4, 2026 (v1.0)
**Purpose:** Ensure agents systematically analyze ALL repercussions before completing any code change.

---

## 🚨 CRITICAL: Read Before Any Modification

This protocol is **MANDATORY** for all AI agents (Claude, Copilot, Gemini, etc.) working on ZebTrack-AI. Failure to follow these steps results in incomplete changes that break system coherence.

---

## 1. Impact Analysis Workflow (REQUIRED)

### 1.1. Before Making ANY Change

```text
┌─────────────────────────────────────────────────────────────────┐
│ 1. IDENTIFY the change type (see Section 2)                    │
│ 2. RUN the mandatory trace commands (see Section 3)            │
│ 3. MAP all affected components (use impact_analyzer.py)        │
│ 4. VERIFY tests exist for affected domains                     │
│ 5. MAKE the change                                             │
│ 6. RUN domain-specific tests                                   │
│ 7. UPDATE documentation if contracts changed                   │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2. After Completing the Change

- [ ] All affected files have been modified consistently
- [ ] Event payloads match `docs/reference/system_integration.md` contracts
- [ ] DI chain is complete (settings passed through all constructors)
- [ ] Serialization/deserialization chains are symmetric
- [ ] Domain tests pass (`pytest -m "<domain>"`)
- [ ] Documentation updated if public API changed

---

## 2. Change Type Classification

### 2.1. Event Changes (HIGH RISK)

**Indicators:** Modifying `Events` class, `UIEvents` enum, or event payloads.

**Mandatory Checks:**

- [ ] All subscribers of the event
- [ ] All publishers of the event
- [ ] Payload structure matches all handlers
- [ ] EventBus version (v1 vs v2) is correct

**Trace Commands:**

```bash
# Find all event subscribers
scripts/impact_analyzer.py event EVENT_NAME

# Manual grep backup
grep -rn "Events.EVENT_NAME\|'EVENT_NAME'\|\"EVENT_NAME\"" src/zebtrack/
grep -rn "subscribe.*EVENT_NAME\|on_.*EVENT_NAME" src/zebtrack/
```

### 2.2. Settings/Configuration Changes (MEDIUM RISK)

**Indicators:** Modifying `settings.py`, `config.yaml`, or injected `settings_obj`.

**Mandatory Checks:**

- [ ] Pydantic model in `settings.py`
- [ ] Default in `config.yaml`
- [ ] Injection in `__main__.py` Composition Root
- [ ] All services that receive `settings_obj`

**Trace Commands:**

```bash
scripts/impact_analyzer.py settings SETTING_PATH
```

### 2.3. Data Structure Changes (HIGH RISK)

**Indicators:** Modifying models, dataclasses, Parquet schema, or serialization.

**Mandatory Checks:**

- [ ] Serialization method (to_dict, serialize)
- [ ] Deserialization method (from_dict, deserialize)
- [ ] All consumers of the data structure
- [ ] Parquet column order (IMMUTABLE - see Section 4.1)

**Trace Commands:**

```bash
scripts/impact_analyzer.py class ClassName
```

### 2.4. UI Component Changes (MEDIUM RISK)

**Indicators:** Modifying widgets, dialogs, or view methods.

**Mandatory Checks:**

- [ ] `root.after()` for all UI updates from non-main threads
- [ ] Event subscriptions in `EventDispatcher`
- [ ] Tab-aware behavior (analysis vs zone tab)

**Trace Commands:**

```bash
scripts/impact_analyzer.py file path/to/changed_file.py
```

### 2.5. Service/Coordinator Changes (HIGH RISK)

**Indicators:** Modifying coordinator methods or adding dependencies.

**Mandatory Checks:**

- [ ] Constructor injection chain from `__main__.py`
- [ ] Callback signatures (see Pitfall #14)
- [ ] Thread safety for StateManager updates

**Trace Commands:**

```bash
scripts/impact_analyzer.py class CoordinatorName
scripts/impact_analyzer.py di
```

### 2.6. Multi-Aquarium Changes (CRITICAL RISK)

**Indicators:** Anything touching `MultiAquariumZoneData`, aquarium IDs, or partitioned detection.

**Mandatory Checks:**

- [ ] Use `get_multi_aquarium_zone_data()` not `get_zone_data()`
- [ ] Serialization via `ZoneManager.multi_aquarium_zone_data_to_dict`
- [ ] Track ID convention: `aquarium_id * 1000 + local_track_id`
- [ ] Output directory structure: `<video>_aquarium_N/`

**Trace Commands:**

```bash
scripts/impact_analyzer.py class MultiAquariumZoneData
scripts/impact_analyzer.py event ZONE_MULTI_AUTO_DETECT
```

---

## 3. Mandatory Trace Commands

### 3.1. Impact Analyzer Tool (PREFERRED)

```bash
# Analyze impact of changing a specific file
python scripts/impact_analyzer.py file src/zebtrack/path/to/file.py

# Analyze impact of changing a class
python scripts/impact_analyzer.py class ClassName

# Analyze impact of changing an event
python scripts/impact_analyzer.py event EVENT_NAME

# Analyze impact of changing a function
python scripts/impact_analyzer.py function function_name

# Show DI injection chain
python scripts/impact_analyzer.py di

# Show full dependency graph (outputs DOT format)
python scripts/impact_analyzer.py graph
```

### 3.2. Manual Grep Backup Commands

When the analyzer is insufficient, use these manual searches:

```bash
# Find all imports of a module
grep -rn "from zebtrack.path import\|import zebtrack.path" src/

# Find all usages of a class
grep -rn "ClassName\|class ClassName" src/

# Find all event publishers
grep -rn "publish.*EVENT\|publish_event.*EVENT" src/

# Find all event subscribers
grep -rn "subscribe.*EVENT\|on_.*EVENT" src/

# Find all settings usage
grep -rn "settings_obj\.\|settings\." src/zebtrack/
```

---

## 4. Immutable Contracts (NEVER CHANGE)

### 4.1. Parquet Schema

```text
timestamp, frame, track_id, x1, y1, x2, y2, confidence, [x_center_px, y_center_px, x_cm, y_cm]
```

**Rule:** Column order is FIXED. Any schema changes require:

1. Migration script
2. Version bump
3. Backward compatibility layer
4. Update `tests/test_recorder.py`

### 4.2. Track ID Convention (Multi-Aquarium)

```text
Global Track ID = aquarium_id * 1000 + local_track_id
```

- Aquarium 0: 0-999
- Aquarium 1: 1000-1999
- Aquarium 2: 2000-2999

### 4.3. Event Bus Separation

| Bus             | Event Type             | Use For                                   |
| --------------- | ---------------------- | ----------------------------------------- |
| `EventBus` (v1) | `Events` class strings | Domain events (recording, project, model) |
| `EventBusV2`    | `UIEvents` enum        | UI component sync (zones, canvas)         |

**NEVER mix them.**

---

## 5. Domain-Specific Test Requirements

After making changes, run the appropriate test suite:

| Change Domain  | Test Command                                              | Minimum Coverage                                  |
| -------------- | --------------------------------------------------------- | ------------------------------------------------- |
| UI/Widgets     | `pytest -m gui -n0`                                       | All GUI tests pass                                |
| Processing     | `pytest tests/test_processing*.py tests/test_recorder.py` | No regressions                                    |
| Multi-Aquarium | `pytest -k "multi_aquarium or partitioned"`               | All MA tests pass                                 |
| Events         | `pytest tests/test_event*.py tests/coordinators/`         | All coordinator tests                             |
| Settings       | `pytest tests/test_settings.py`                           | Settings tests pass                               |
| Analysis       | `pytest tests/test_analysis*.py tests/test_reporter*.py`  | Analysis tests pass                               |
| **Full Suite** | `pytest -m "" -n0`                                        | 40% overall coverage (Linux CI); 0% on Windows CI |

---

## 6. Serialization Chain Verification

For any data structure that crosses process/thread boundaries:

```text
┌─────────────────────────────────────────────────────────────────┐
│ Component A                                                     │
│   └── serialize() / to_dict()                                   │
│         └── Queue / File / Network                              │
│               └── deserialize() / from_dict()                   │
│                     └── Component B                             │
└─────────────────────────────────────────────────────────────────┘
```

**Verification Checklist:**

- [ ] `to_dict()` output matches `from_dict()` input expectations
- [ ] All fields are preserved (no silent drops)
- [ ] Type conversions are symmetric (str → int → str)
- [ ] Optional fields have default values on deserialize

### 6.1. Known Serialization Chains

| Data                    | Serializer                                     | Deserializer                                     | Location          |
| ----------------------- | ---------------------------------------------- | ------------------------------------------------ | ----------------- |
| `ZoneData`              | `ZoneManager.zone_data_to_dict`                | `ZoneManager.zone_data_from_dict`                | Processing Worker |
| `MultiAquariumZoneData` | `ZoneManager.multi_aquarium_zone_data_to_dict` | `ZoneManager.multi_aquarium_zone_data_from_dict` | Processing Worker |
| `ProcessingContext`     | `ProcessingCoordinator._create_context`        | `ProcessingWorker.__init__`                      | Worker spawn      |
| `Settings`              | `settings.model_dump()`                        | `Settings(**dict)`                               | Config files      |

---

## 7. DI Injection Chain Verification

For any new service or dependency:

```text
┌─────────────────────────────────────────────────────────────────┐
│ config.yaml / config.local.yaml                                 │
│   └── load_settings()                                           │
│         └── __main__.py (Composition Root, lines 140-280)       │
│               └── ServiceA(settings_obj=settings)               │
│                     └── ServiceB(settings_obj=settings)         │
│                           └── ... (all consumers)               │
└─────────────────────────────────────────────────────────────────┘
```

**Verification Checklist:**

- [ ] Setting exists in Pydantic model (`settings.py`)
- [ ] Default exists in `config.yaml`
- [ ] Injected in `__main__.py` Composition Root
- [ ] Passed to all services that need it
- [ ] No `from zebtrack import settings` singleton imports

---

## 8. Documentation Update Requirements

When contracts change, update these files:

| Change Type    | File to Update                                            |
| -------------- | --------------------------------------------------------- |
| Event payload  | `docs/reference/system_integration.md`                    |
| New event      | `docs/reference/system_integration.md` Section 2-3        |
| DI pattern     | `docs/explanation/dependency_injection.md`                |
| Settings       | `config.yaml` + `docs/reference/operational_reference.md` |
| API signature  | Inline docstrings + `docs/reference/api/` if public       |
| Architecture   | `docs/explanation/architecture.md`                        |
| Common pitfall | `docs/reference/system_integration.md` Section 6          |

---

## 9. Quick Reference: Common Pitfalls

See `docs/reference/system_integration.md` Section 6 for the full list (19 documented pitfalls).

**Top 5 Most Common Agent Errors:**

1. **Missing event payload keys** → UI crash or silent failure
2. **Using `get_zone_data()` for multi-aquarium** → Aquarium 1 gets wrong data
3. **Forgetting `root.after()` for UI updates** → Thread safety violation
4. **Not rescaling zones after video dimensions known** → Zones in wrong position
5. **Singleton settings import** → Tests fail, DI broken

---

## 10. Agent Workflow Summary

```text
┌─────────────────────────────────────────────────────────────────┐
│ BEFORE CODING:                                                  │
│   1. Identify change type (Section 2)                           │
│   2. Run: python scripts/impact_analyzer.py <type> <name>       │
│   3. Read affected files from analyzer output                   │
│   4. Check docs/reference/system_integration.md for contracts   │
│                                                                 │
│ WHILE CODING:                                                   │
│   5. Modify ALL affected components (not just the target)       │
│   6. Maintain serialization symmetry                            │
│   7. Preserve DI injection chains                               │
│                                                                 │
│ AFTER CODING:                                                   │
│   8. Run domain-specific tests (Section 5)                      │
│   9. Update docs/reference/system_integration.md if contracts changed │
│  10. Verify no "no handlers" warnings in logs                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Appendix A: Related Documentation

- [system_integration.md](../../reference/system_integration.md) - Event contracts and component dependencies
- [dependency_injection.md](../../explanation/dependency_injection.md) - DI patterns and error handling
- [architecture.md](../../explanation/architecture.md) - System architecture overview
- [state_management.md](../../explanation/state_management.md) - StateManager patterns

## Appendix B: Tool Installation

The impact analyzer is included in the project:

```bash
# No installation needed - uses standard library + AST parsing
python scripts/impact_analyzer.py --help
```

---

_This protocol was created to prevent incomplete changes that cause system incoherence. All agents MUST follow this workflow._
