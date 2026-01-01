# ADR-008: Live Camera Multi-Aquarium Support with Hardware-Based Fallbacks

**Status:** Accepted  
**Date:** 2026-01-01  
**Version:** 2.2.0

## Context

Live camera sessions in ZebTrack-AI v2.1 supported only single-aquarium processing. Users with multiple aquariums needed to:
1. Run separate sessions sequentially (lost temporal synchronization)
2. Process offline after recording (delayed feedback)
3. Manually crop/split videos post-capture (error-prone)

Additionally, no hardware capability assessment existed, leading to:
- Frame drops and crashes on low-end systems
- Poor user experience with no guidance on system requirements
- Silent failures during high-load scenarios

## Decision

Implement **hardware-aware multi-aquarium live processing** with automatic fallback options:

### 1. Hardware Capability Detection (`hardware_capability.py`)
- **5-Tier Classification:**
  - EXCELLENT: GPU + 8+ cores + 16GB RAM → 4+ aquariums
  - GOOD: 6+ cores + 8GB RAM → 2-3 aquariums
  - MODERATE: 4+ cores + 6GB RAM → 2 aquariums
  - LIMITED: 2-3 cores or <6GB RAM → 1 aquarium
  - INSUFFICIENT: <2 cores or <4GB RAM → record-only

- **Metrics:** CPU cores, available RAM, GPU presence, current load
- **Output:** `HardwareCapabilityReport` with recommendations and warnings

### 2. Live Camera Modes (`live_camera_mode.py`)
Four processing modes with automatic selection:

| Mode | Description | Hardware Required |
|------|-------------|-------------------|
| `MULTI_AQUARIUM_REALTIME` | Process N aquariums simultaneously | MODERATE+ for N aquariums |
| `SINGLE_AQUARIUM_REALTIME` | Process 1 aquarium only | LIMITED+ (2 cores, 6GB) |
| `SEQUENTIAL_AQUARIUM` | Record N sessions, 1 per aquarium | LIMITED+ (per session) |
| `RECORD_ONLY` | Save video, process offline | ANY (no real-time detection) |

### 3. User Workflow Integration

**Wizard Phase (LiveConfigStep):**
```
User selects: 3 aquariums
↓
HardwareCapabilityDetector.assess_capability()
↓
LiveCameraModeSelector.recommend_mode(requested=3)
↓
If INSUFFICIENT:
  → Show dialog: "Sistema insuficiente. Opções:"
    • Gravar sem detecção (record-only)
    • Processar 1 aquário apenas
    • Dividir em 3 sessões
    • Cancelar e fazer upgrade
↓
User chooses → Wizard adapts config
```

**Session Start:**
```
LiveCameraCoordinator.start_live_session(mode=MULTI_AQUARIUM_REALTIME)
↓
If mode == MULTI_AQUARIUM:
  → Use detect_partitioned_parallel() (ThreadPoolExecutor)
  → Write partitioned detection data
  → Track per-aquarium metrics
Else if mode == SINGLE_AQUARIUM:
  → Standard detect() with single zone
Else if mode == RECORD_ONLY:
  → Skip detector, only record video
```

### 4. Camera Disconnect Recovery

**Problem:** Camera USB disconnects during 30min+ sessions caused:
- Silent data gaps (continued with cached detections)
- Invalid trajectory data
- No user notification

**Solution:**
- **Detection:** Track `last_valid_frame_time`; gap >2s = disconnect
- **Action:** Pause recorder, publish `CAMERA_DISCONNECT_DETECTED` event
- **UI:** Show `CameraDisconnectRecoveryDialog` with options:
  - Wait 30s for auto-reconnect
  - Resume manually after user intervention
  - Stop session and save data
- **Metadata:** Record gap timestamps in report

### 5. Batch Report Generation

**Problem:** No unified reports across multiple live sessions (same experiment group).

**Solution:**
- `LiveBatchCoordinator` tracks sessions with same `group/day/subject_id`
- After last session, auto-generates unified Excel (aggregated metrics)
- Persists via `ProjectManager.register_batch_outputs()`
- Publishes `BATCH_ANALYSIS_COMPLETED` event

## Consequences

### Positive
✅ **Multi-Aquarium Support:** Process 2-6 aquariums simultaneously (hardware-dependent)  
✅ **Graceful Degradation:** Automatic fallback to single-aquarium or record-only  
✅ **User Transparency:** Clear hardware requirements and recommendations  
✅ **Disconnect Recovery:** No silent data corruption; user-guided recovery  
✅ **Unified Reporting:** Cross-session aggregation for batch experiments  
✅ **Sequential Mode:** Alternative for low-end hardware (1 aquarium per session)

### Negative
⚠️ **Complexity Increase:** 4 processing modes vs 1 (testing burden)  
⚠️ **Hardware Detection Accuracy:** Heuristics may misclassify edge cases  
⚠️ **UI Overhead:** New dialogs (recovery, progress, mode selection)  
⚠️ **Migration Path:** Existing projects assume single-aquarium (need schema versioning)

### Neutral
- Record-only mode bypasses all detection (useful for storage-first workflows)
- Sequential mode requires user to manually switch cameras/positions between sessions
- Multi-aquarium detection uses same `detect_partitioned_parallel` as offline processing

## Implementation Files

**New Modules:**
- `src/zebtrack/utils/hardware_capability.py` - Capability detection
- `src/zebtrack/core/live_camera_mode.py` - Mode selection logic
- `src/zebtrack/coordinators/live_batch_coordinator.py` - Batch tracking
- `src/zebtrack/ui/dialogs/camera_disconnect_recovery_dialog.py` - Recovery UI
- `src/zebtrack/ui/dialogs/aquarium_detection_progress_dialog.py` - Arena detection UI

**Modified Modules:**
- `src/zebtrack/core/live_camera_service.py` - Disconnect detection, mode support
- `src/zebtrack/io/recorder.py` - Pause/resume methods
- `src/zebtrack/core/project_manager.py` - Batch output persistence

## Alternatives Considered

### A. Always Use Record-Only for Multi-Aquarium
**Rejected:** Defeats purpose of "live" analysis; users want real-time feedback.

### B. Require GPU for Multi-Aquarium
**Rejected:** Excludes majority of users; CPU-only systems can handle 2-3 aquariums with optimizations.

### C. Automatic Hardware Upgrade Prompts
**Rejected:** Out of scope; users should decide hardware investments independently.

### D. Cloud Processing Offload
**Rejected:** Requires internet, privacy concerns, cost barriers.

## Testing Strategy

**Unit Tests:**
- `HardwareCapabilityDetector` with mocked psutil (CPU/RAM variations)
- `LiveCameraModeSelector` recommendation logic (all scenarios)
- `Recorder.pause_recording()` / `resume_recording()`

**Integration Tests:**
- End-to-end: wizard → multi-aquarium session → batch report
- Camera disconnect → recovery → session completion
- Aquarium detection progress → consensus → zone save

**Performance Tests:**
- Multi-aquarium frame drop rates (2-6 aquariums)
- Memory usage over 30min sessions
- Disconnect recovery time (reconnect latency)

## Migration Guide

**Existing Projects (v2.1):**
- No schema changes required
- Multi-aquarium is opt-in (wizard selection)
- Single-aquarium sessions work identically

**New Projects (v2.2):**
- Wizard includes hardware check step
- Mode selection dialog shown if requested > supported
- `project_data.json` includes `live_camera_mode` field

## References

- Hardware benchmarks: `docs/performance/LIVE_CAMERA_BENCHMARKS.md`
- Mode selection flow: `docs/guides/developer/LIVE_CAMERA_MODES.md`
- Disconnect recovery: `docs/guides/user/CAMERA_TROUBLESHOOTING.md`
- ADR-004: Live Camera Display Divergence (canvas vs preview window)
