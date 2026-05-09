---
description: Run impact_analyzer.py to identify components affected by a change
argument-hint: <type> <name>   # type ∈ {file, class, function, event, settings, di, graph}
allowed-tools: Bash(poetry run python scripts/impact_analyzer.py:*), Bash(python scripts/impact_analyzer.py:*)
---

Run the project's impact analyzer for: `$ARGUMENTS`

```bash
poetry run python scripts/impact_analyzer.py $ARGUMENTS
```

After it completes, summarize the findings:

1. List the components flagged as affected.
2. Cross-check against [`.copilot-impact-map.yaml`](../../.copilot-impact-map.yaml) for related events/serialization chains.
3. Identify which test files in [`docs/testing/TEST_MAP.md`](../../docs/testing/TEST_MAP.md) cover those components.
4. Stop and ask the user before making any code change.

Examples:

- `/impact class WeightManager` — find everything that depends on `WeightManager`
- `/impact file src/zebtrack/coordinators/multi_aquarium_coordinator.py`
- `/impact event ZONE_PROCESSING_MODE_CHANGED`
- `/impact function get_multi_aquarium_zone_data`
