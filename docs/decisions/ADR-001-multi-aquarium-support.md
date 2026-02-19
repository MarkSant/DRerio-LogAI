# ADR-001: Multi-Aquarium Support Architecture

**Status**: Accepted
**Decision Date**: December 2025
**Phases**: 10, 10.1, 11

## Context

ZebTrack-AI initially supported only single-aquarium video analysis.
Research protocols frequently require simultaneous recording of multiple
aquariums in a single video frame (typically 2) to reduce equipment
costs and ensure identical environmental conditions across subjects.

Key requirements:

1. Detect and isolate 2+ aquariums automatically from a single video.
2. Track subjects independently within each aquarium.
3. Generate per-aquarium reports, trajectories, and behavioral metrics.
4. Support both parallel (1 video pass) and sequential (N video passes)
   processing modes.
5. Maintain backward compatibility with single-aquarium workflows.

## Decision

### Data Model

Introduced three new data structures in `core/detection/detection_types.py`:

- **`AquariumData`**: Per-aquarium zone configuration with experimental
  metadata (group, subject_id, day, roi_mode, roi_data).
- **`MultiAquariumZoneData`**: Container for multiple `AquariumData`
  instances with `sequential_processing` flag and video dimensions.
- **`ZoneData`**: Unchanged — remains the canonical single-aquarium type.
  `AquariumData.to_zone_data()` converts for backward compatibility.

### Track ID Convention

Global track ID = `aquarium_id * 1000 + local_track_id`.

- Aquarium 0: IDs 0–999
- Aquarium 1: IDs 1000–1999
- Aquarium 2: IDs 2000–2999

`local_track_id` must be < 1000 to prevent overflow collisions.

### Processing Modes

- **Parallel** (`sequential_processing=False`): Both aquariums processed
  in a single video pass. Uses `detect_partitioned_parallel()` with
  `ThreadPoolExecutor` for ~30–40% speedup.
- **Sequential** (`sequential_processing=True`, default): Each aquarium
  gets a complete video pass. Reuses the battle-tested single-aquarium
  code path. Lower memory, better precision, 2× processing time.

### Serialization

`ZoneManager.multi_aquarium_zone_data_to_dict()` /
`multi_aquarium_zone_data_from_dict()` handle serialization for project
persistence and worker thread communication.

### Backward Compatibility

- `ProjectManager.get_zone_data()` returns only Aquarium 0 data (legacy).
- `ProjectManager.get_multi_aquarium_zone_data()` returns full multi-data.
- Report generation **must** use `get_multi_aquarium_zone_data()` to avoid
  Aquarium 1 using Aquarium 0's cropped background image.

## Consequences

### Positive

- Researchers can analyze 2 aquariums per video without manual splitting.
- Per-aquarium ROI, calibration, and reporting are fully independent.
- Sequential mode offers precision; parallel mode offers speed.
- Single-aquarium workflows are completely unaffected.

### Negative

- Track ID convention limits each aquarium to 1000 simultaneous tracks
  (sufficient for zebrafish, may need revision for other species).
- Dual processing modes increase testing surface area.
- `get_zone_data()` vs `get_multi_aquarium_zone_data()` API split is a
  common source of bugs — must always use the multi variant in
  reporting/analysis contexts.

### Testing

250+ tests across `tests/core/test_*_multi*.py`,
`tests/ui/test_*_multi*.py`, `tests/integration/test_multi_aquarium_e2e.py`.

## References

- `src/zebtrack/core/detection/detection_types.py` (data structures)
- `src/zebtrack/core/detection/single_detector.py` (partitioned detection)
- `src/zebtrack/coordinators/processing_coordinator.py` (sequential flow)
- `src/zebtrack/core/project/project_manager.py` (persistence)
- `docs/testing/MULTI_AQUARIUM_STATUS.md`
