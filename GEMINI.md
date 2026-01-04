# Gemini Project Context: ZebTrack-AI

Zebrafish tracking and behavioral analysis application using YOLO/OpenVINO, Tkinter GUI, and
event-driven architecture with dependency injection.

---

## 🚨 MANDATORY: Impact Analysis Protocol

**BEFORE making ANY code change**, you MUST:

1. **Read**: [`docs/architecture/IMPACT_ANALYSIS_PROTOCOL.md`](docs/architecture/IMPACT_ANALYSIS_PROTOCOL.md)
2. **Run**: `python scripts/impact_analyzer.py <type> <name>` - Identify affected components
3. **Consult**: [`.copilot-impact-map.yaml`](.copilot-impact-map.yaml) - Quick dependency lookup
4. **Verify**: Update ALL affected components consistently
5. **Test**: Run domain-specific tests

**Incomplete impact analysis leads to system incoherence.**

---

## Quick Reference

| Command | Purpose |
|---------|---------|
| `poetry install` | Setup environment |
| `poetry run zebtrack` | Run application |
| `poetry run pytest` | Run tests |
| `poetry run ruff check . --fix` | Lint and fix |
| `python scripts/impact_analyzer.py <type> <name>` | **Trace change impact** |

## Architecture Essentials

- **State**: Immutable `StateManager` (see `docs/architecture/STATE_MANAGEMENT_GUIDE.md`)
- **Events**: `EventBus` for cross-component communication
- **Coordinators**: `ProcessingCoordinator`, `HardwareCoordinator`, `SessionCoordinator`,
  `ProjectLifecycleCoordinator`
- **Multi-Aquarium**: Track ID = `aquarium_id * 1000 + local_track_id`

## Critical Rules

1. **Read `docs/architecture/SYSTEM_INTEGRATION_MAP.md`** before debugging integration issues
2. **Test everything** with pytest
3. **Update SYSTEM_INTEGRATION_MAP.md** when modifying events, payloads, or dependencies
4. **Check for infinite event loops** when adding subscriptions to `MainViewModel`
5. **MultiAquariumZoneData compatibility**: Always check when modifying `ProjectManager`/`ZoneManager`
6. **Unified Reports (v3.3)**: Use `reports.delete_unified` for cleanup; rely on `group_id`, not `group`

## Multi-Aquarium Checklist

When working with multi-aquarium features:

- [ ] Use `get_multi_aquarium_zone_data()` not `get_zone_data()` for reports
- [ ] Check for `MultiAquariumZoneData` before accessing `.polygon`
- [ ] Use `EventBus.publish_event()` (not `publish()`)
- [ ] Register outputs via `ProjectManager.register_multi_aquarium_outputs()`

## Documentation Structure

| Folder | Purpose |
|--------|---------|
| `docs/architecture/` | System design, events, DI |
| `docs/guides/developer/` | Developer workflows |
| `docs/guides/user/` | End-user docs (English) |
| `docs/wiki/` | User guides (Portuguese) |
| `docs/archive/` | Historical docs and fixes |

## Agent Protocol

- **Planning**:
  1. **MANDATORY**: Run `python scripts/impact_analyzer.py` first
  2. Check `SYSTEM_INTEGRATION_MAP.md` for contracts
  3. Consult `.copilot-impact-map.yaml` for dependency graphs
- **Execution**: Ensure `MultiAquariumZoneData` compatibility
- **Verification**:
  1. Run domain-specific tests (see `IMPACT_ANALYSIS_PROTOCOL.md`)
  2. Verify reports (Word/Excel) after analysis changes
  3. Confirm ALL affected components from analyzer are updated

---

*Historical fixes archived to `docs/archive/fixes/DEC_2025_CRITICAL_FIXES.md`*
*Impact Analysis Protocol: `docs/architecture/IMPACT_ANALYSIS_PROTOCOL.md`*
