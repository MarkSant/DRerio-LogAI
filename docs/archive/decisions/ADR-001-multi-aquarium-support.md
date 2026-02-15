# ADR-001: Multi-Aquarium Support

## Status

**Accepted** - December 2024

## Context

ZebTrack-AI is a desktop application for tracking zebrafish in laboratory video recordings.
The original architecture supported only single-aquarium videos (one fish per video).

Research requirements now include:
1. Recording two aquariums side-by-side in a single video
2. Each aquarium contains exactly one animal
3. Aquariums may belong to different experimental groups (e.g., Control vs CBD treatment)
4. Each animal needs separate tracking data and analysis reports
5. Output organization should reflect experimental structure (Group/Day/Subject)

## Decision

We will implement multi-aquarium support with the following design decisions:

### 1. Fixed Support for 2 Aquariums

**Decision**: Support exactly 2 aquariums (not N generic aquariums).

**Rationale**:
- Matches current experimental setup (side-by-side dual tanks)
- Simplifies UI design (left/right assignment)
- Reduces complexity in tracking coordination
- Future extension to N aquariums remains possible

### 2. Independent ByteTrackers per Aquarium

**Decision**: Each aquarium gets its own ByteTracker instance.

**Rationale**:
- Prevents ID collision between aquariums
- Isolates tracking state (no cross-contamination)
- Simplifies trajectory storage
- Enables per-aquarium confidence thresholds

### 3. Track ID Offset Convention

**Decision**: Global track IDs use formula `aquarium_id * 1000 + local_id`.

**Example**:
- Aquarium 0, Track 1 → ID 1
- Aquarium 0, Track 2 → ID 2
- Aquarium 1, Track 1 → ID 1001
- Aquarium 1, Track 2 → ID 1002

**Rationale**:
- Unique IDs across entire video
- Easy to recover aquarium ID from global ID
- Compatible with existing Recorder schema
- 1000 tracks per aquarium is more than sufficient

### 4. Separate Output Files per Subject

**Decision**: Each subject (aquarium) gets its own output directory with tracking and analysis files.

**Structure**:
```
project/
├── Grupo_Controle/
│   └── Dia_01/
│       └── S01/
│           ├── video_tracking.parquet
│           ├── 1_summary.xlsx
│           └── 2_detailed_report.docx
└── Grupo_CBD/
    └── Dia_01/
        └── S02/
            ├── video_tracking.parquet
            ├── 1_summary.xlsx
            └── 2_detailed_report.docx
```

**Rationale**:
- Matches experimental organization
- Enables independent analysis per subject
- Simplifies data management
- Compatible with multi-video batch processing

### 5. Contour-Based Auto-Detection

**Decision**: Auto-detect aquariums using contour analysis on first frame.

**Algorithm**:
1. Convert frame to grayscale
2. Apply adaptive thresholding
3. Find external contours
4. Filter by area (minimum tank size)
5. Sort horizontally (left = Aquarium 0, right = Aquarium 1)
6. Generate rectangular bounding polygons

**Rationale**:
- Works with typical lab setups (bright tanks on dark background)
- No ML model required
- User can adjust manually after detection
- Fast execution (single frame)

### 6. Data Models

**New Dataclasses**:

```python
@dataclass
class AquariumData:
    id: int  # 0 or 1
    polygon: list[tuple[int, int]]  # Bounding polygon
    roi_polygons: list[list[tuple[int, int]]] = field(default_factory=list)
    roi_names: list[str] = field(default_factory=list)
    roi_colors: list[tuple[int, int, int]] = field(default_factory=list)
    group: str = ""  # Experimental group
    subject_id: str = ""  # Subject identifier
    day: int = 1  # Experimental day

@dataclass
class MultiAquariumZoneData:
    aquariums: list[AquariumData] = field(default_factory=list)
    video_width: int = 0
    video_height: int = 0
```

**Rationale**:
- Clear separation of per-aquarium configuration
- Backward compatible (single aquarium = list with 1 element)
- Includes all metadata for output organization

## Consequences

### Positive

1. **Efficiency**: Process two aquariums in single video pass
2. **Organization**: Clear output structure matching experiments
3. **Flexibility**: Per-aquarium groups and settings
4. **Simplicity**: Fixed 2-aquarium limit reduces edge cases
5. **Compatibility**: Track ID offset preserves existing Parquet schema

### Negative

1. **Limitation**: Cannot handle N>2 aquariums (requires future extension)
2. **Complexity**: More UI states to manage (multi vs single mode)
3. **Testing**: Additional test cases for multi-aquarium paths
4. **Memory**: Two ByteTrackers consume more RAM

### Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Auto-detection fails on unusual setups | Manual polygon editing always available |
| Track ID collision at 1000 boundary | Assert local_id < 1000 at runtime |
| Overlapping aquarium polygons | Validation in WizardService |
| Performance with two trackers | Profile and optimize if needed |

## Implementation Phases

1. **Phase 0-1**: Core data models (`AquariumData`, `MultiAquariumZoneData`)
2. **Phase 2-3**: ZoneManager integration, auto-detection
3. **Phase 4-5**: DetectorService partitioning, ByteTracker isolation
4. **Phase 6-7**: Recorder multi-output, ProcessingWorker adaptation
5. **Phase 8-9**: ProjectManager file hierarchy, WizardService validation
6. **Phase 10-11**: AnalysisService per-aquarium, visualization overlay
7. **Phase 12-13**: E2E tests, documentation
8. **Phase 14-15**: Test updates, validation, merge

## Multi-Aquarium v2 Enhancements (January 2025)

### Phase 1: Foundation
- **ROI Cropping**: `_crop_aquarium_region()` for per-aquarium frame extraction
- **Uncertainty Metrics**: Added `uncertainty` (1 - confidence) column to Parquet
- **Export Scripts**: `export_r_script()` and `export_python_script()` for statistical analysis
- **Thigmotaxis**: Edge-preference metrics in `data_transformer.py`
- **Feather Export**: `export_feather()` for R integration

### Phase 2: Performance
- **Parallel Detection**: `detect_partitioned_parallel()` with ThreadPoolExecutor (~30-40% speedup)
- **Batch Inference**: `detect_batch()` for offline processing optimization
- **Metrics Cache**: Caching for frequently-accessed detection metrics

### Phase 3: UI/UX
- **Side-by-Side Preview**: `create_side_by_side_preview()` for visual comparison
- **Enhanced Validation**: `validate_multi_aquarium_config()` returns (is_valid, errors, warnings)

### Phase 4: Robustness
- **Per-Aquarium Tracking Validation**: `_validate_multi_aquarium_ids()` in TrajectoryQualityValidator
- **Gap Detection**: `_detect_per_aquarium_gaps()` for missing frame detection per aquarium
- **Error Recovery**: Fallback mechanism when detection fails for individual aquariums
- **IoU Tracking**: `bbox_iou` column for tracking stability analysis

### Phase 5: Event System
- **New Events**:
  - `ZONE_MULTI_AUTO_DETECT_SUCCESS` - Detection succeeded with polygons
  - `ZONE_MULTI_AUTO_DETECT_FAILED` - Detection failed with reason
  - `ZONE_AQUARIUM_CONFIG_UPDATED` - Individual aquarium config changed
- **New Handlers**:
  - `ProcessingCoordinator._handle_multi_auto_detect()`
  - `ProjectLifecycleCoordinator._handle_aquarium_config_updated()`

### Phase 6: Sequential Processing (December 2025)
**Feature**: Option to process each aquarium separately with 2 complete video passes.

- **New Field**: `MultiAquariumZoneData.sequential_processing: bool`
  - `False` (default): Parallel mode - both aquariums processed in 1 video pass
  - `True`: Sequential mode - complete video for aquarium 0, then aquarium 1

- **New Event**: `ZONE_PROCESSING_MODE_CHANGED`
  - Payload: `{sequential: bool}`
  - Emitted by `ZoneControls` radio button toggle

- **New Methods** (in `ProcessingCoordinator`):
  - `_start_sequential_multi_aquarium_processing()` - Initialize sequential context
  - `_process_next_aquarium_in_sequence()` - Process next aquarium, finalize when done
  - `_start_single_aquarium_for_sequential()` - Run single-aquarium flow for each

- **UI Toggle**: Radio buttons in ZoneControls
  - "Simultâneo (1 passagem, mais rápido)"
  - "Sequencial (2 passagens, 1 aquário por vez)"

- **Report Generation**: Automatic Word, Excel, and Parquet summary generation for each aquarium

- **Serialization**: `ZoneManager.multi_aquarium_zone_data_to_dict/from_dict()` updated

**Advantages**:
- 100% resources per aquarium (no splitting)
- Lower memory (1 ByteTracker at a time)
- Reuses battle-tested single-aquarium code path

**Trade-offs**:
- 2x total processing time
- Video read twice from disk

## References

- [PLANO_MULTI_AQUARIUM.md](../../PLANO_MULTI_AQUARIUM.md) - Detailed implementation plan
- [ARCHITECTURE.md](../architecture/ARCHITECTURE.md) - System architecture
- [ByteTrack Paper](https://arxiv.org/abs/2110.06864) - Tracker algorithm

## Revision History

| Date | Version | Author | Changes |
|------|---------|--------|---------|
| 2024-12 | 1.0 | Development Team | Initial ADR |
| 2025-01 | 2.0 | Development Team | Multi-Aquarium v2 (Phases 1-5) |
| 2025-12 | 2.1 | Development Team | Phase 6: Sequential Processing |
