---
description: Checklist for multi-aquarium feature changes
---

# Multi-Aquarium Feature Workflow

// turbo-all

## Pre-Implementation Checklist

1. Read `docs/reference/system_integration.md`
2. Check if feature touches `ProjectManager` or `ZoneManager`
3. Identify affected events in EventBus

## Implementation Rules

### Zone Data Handling

- Use `get_multi_aquarium_zone_data()` for reports (NOT `get_zone_data()`)
- Check for `MultiAquariumZoneData` type before accessing `.polygon`
- Track IDs follow: `aquarium_id * 1000 + local_track_id`

### Event Publishing

- Use `EventBus.publish_event()` (not `publish()`)
- Register outputs: `ProjectManager.register_multi_aquarium_outputs()`

### Serialization

- Multi-aquarium: `ZoneManager.multi_aquarium_zone_data_to_dict()`
- Single aquarium: `ZoneManager.zone_data_to_dict()`

## Testing

Run related tests:

```bash
poetry run pytest tests/test_multi_aquarium*.py -v
poetry run pytest -k "multi" -v
```

## Documentation

Update `docs/reference/system_integration.md` if adding:

- New events
- New payload fields
- New cross-component dependencies
