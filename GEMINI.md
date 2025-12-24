# Gemini Project Context: ZebTrack-AI

Zebrafish tracking and behavioral analysis application using YOLO/OpenVINO, Tkinter GUI, and
event-driven architecture with dependency injection.

## Quick Reference

| Command | Purpose |
|---------|---------|
| `poetry install` | Setup environment |
| `poetry run zebtrack` | Run application |
| `poetry run pytest` | Run tests |
| `poetry run ruff check . --fix` | Lint and fix |

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

- **Planning**: Check `SYSTEM_INTEGRATION_MAP.md` first
- **Execution**: Ensure `MultiAquariumZoneData` compatibility
- **Verification**: Verify reports (Word/Excel) after analysis changes

---

*Historical fixes archived to `docs/archive/fixes/DEC_2025_CRITICAL_FIXES.md`*
