# Live Camera Multi-Aquarium Developer Guide

**Version:** 2.2.0
**Last Updated:** 2026-01-01

## Quick Start

### 1. Hardware Capability Check

```python
from zebtrack.utils.hardware_capability import assess_hardware_for_live_multi_aquarium
from zebtrack.settings import load_settings

settings = load_settings()
report = assess_hardware_for_live_multi_aquarium(settings)

print(report)
# Output:
# Capability: GOOD
# Max Aquariums: 2
# CPU: 6 cores (15.2% used)
# Memory: 12.3GB / 16.0GB available
# GPU: No
# Real-time: Yes
```

### 2. Mode Selection

```python
from zebtrack.core.live_camera_mode import LiveCameraModeSelector

selector = LiveCameraModeSelector(settings)
recommendation = selector.recommend_mode(
    requested_aquariums=3,
    hardware_report=report,
)

print(recommendation.recommended_mode)
# Output: LiveCameraMode.SEQUENTIAL_AQUARIUM (system supports 2, user wants 3)

for mode, desc in recommendation.alternative_options:
    print(f"  {mode.value}: {desc}")
# Output:
#   single_aquarium_realtime: Processar apenas 1 aquário agora
#   record_only: Gravar sem detecção
```

### 3. Start Live Session with Mode

```python
from zebtrack.core.live_camera_mode import LiveCameraMode

# Multi-aquarium (if supported)
success = live_camera_coordinator.start_live_session(
    camera_index=0,
    duration_s=300,
    experiment_id="exp_001",
    mode=LiveCameraMode.MULTI_AQUARIUM_REALTIME,
    aquarium_count=2,
)

# Record-only (no detection)
success = live_camera_coordinator.start_live_session(
    camera_index=0,
    duration_s=300,
    experiment_id="exp_002",
    mode=LiveCameraMode.RECORD_ONLY,
)
```

### 4. Handle Camera Disconnect

```python
from zebtrack.ui.dialogs.camera_disconnect_recovery_dialog import CameraDisconnectRecoveryDialog

def on_disconnect_event(event_data):
    """Called when CAMERA_DISCONNECT_DETECTED event fires."""

    def on_user_action(action):
        if action == "wait":
            # Try auto-reconnect for 30s
            live_camera_service.wait_for_reconnect(timeout_s=30)
        elif action == "resume":
            # User manually fixed camera
            live_camera_service.resume_after_disconnect()
        elif action == "stop":
            # Stop and save
            live_camera_coordinator.stop_live_session()

    # Show dialog
    dialog = CameraDisconnectRecoveryDialog(
        parent=root,
        gap_duration_s=event_data["gap_duration_s"],
        experiment_id=event_data["experiment_id"],
        on_action_callback=on_user_action,
    )
```

### 5. Batch Report Generation

```python
from zebtrack.coordinators.live_batch_coordinator import LiveBatchCoordinator

batch_coordinator = LiveBatchCoordinator(
    project_manager=project_manager,
    analysis_service=analysis_service,
    state_manager=state_manager,
    settings_obj=settings,
    event_bus=event_bus,
)

# Register each session
batch_id = batch_coordinator.register_session(
    experiment_id="exp_001",
    video_path=Path("live_sessions/exp_001/exp_001.mp4"),
    metadata={"group": "G1", "day": "D1", "subject_id": "S01"},
)

# After last session
batch_coordinator.mark_batch_complete(batch_id)
# → Auto-generates unified Excel report
```

## Architecture Overview

```
User Workflow
    ↓
Wizard (LiveConfigStep)
    ↓ assess hardware
HardwareCapabilityDetector
    ↓ recommend mode
LiveCameraModeSelector
    ↓ user confirms
LiveCameraCoordinator.start_live_session(mode=...)
    ↓
LiveCameraService
    ├─ MULTI_AQUARIUM_REALTIME
    │   └→ detect_partitioned_parallel()
    ├─ SINGLE_AQUARIUM_REALTIME
    │   └→ detect() with single zone
    └─ RECORD_ONLY
        └→ Skip detector, record video only
    ↓
Recorder (with pause/resume support)
    ↓
LiveBatchCoordinator
    ↓ (if batch complete)
UnifiedReport.xlsx
```

## Key Components

### HardwareCapabilityDetector
**File:** `src/zebtrack/utils/hardware_capability.py`

**Methods:**
- `assess_capability()` → `HardwareCapabilityReport`
  - Checks CPU cores, RAM, GPU, system load
  - Returns tier: EXCELLENT | GOOD | MODERATE | LIMITED | INSUFFICIENT
  - Recommends max aquariums (0-6)

**Usage:**
```python
detector = HardwareCapabilityDetector(settings_obj)
report = detector.assess_capability()
if report.capability == MultiAquariumCapability.INSUFFICIENT:
    print("Use record-only mode")
```

### LiveCameraModeSelector
**File:** `src/zebtrack/core/live_camera_mode.py`

**Methods:**
- `recommend_mode(requested, hardware_report)` → `LiveCameraModeRecommendation`
  - Compares requested vs supported aquariums
  - Returns recommended mode + alternatives
  - Includes warnings if insufficient

**Modes:**
```python
class LiveCameraMode(Enum):
    MULTI_AQUARIUM_REALTIME = "multi_aquarium_realtime"
    SINGLE_AQUARIUM_REALTIME = "single_aquarium_realtime"
    SEQUENTIAL_AQUARIUM = "sequential_aquarium"
    RECORD_ONLY = "record_only"
```

### LiveCameraService Extensions
**File:** `src/zebtrack/core/live_camera_service.py`

**New Variables:**
```python
self._last_valid_frame_time: float | None  # Disconnect detection
self._camera_disconnect_threshold_s: float = 2.0
self._disconnect_gaps: list[tuple[float, float]]  # Gap timestamps
self._recording_paused: bool  # Recorder pause state
```

**New Methods:**
```python
def _check_camera_disconnect() -> None
    """Detect camera loss (gap > threshold)."""

def _on_camera_reconnected() -> None
    """Resume recording after reconnect."""
```

**Events Published:**
- `CAMERA_DISCONNECT_DETECTED` - When gap > threshold
- `CAMERA_RECONNECTED` - When valid frames resume
- `AQUARIUM_DETECTION_PROGRESS` - During arena detection phase

### Recorder Pause/Resume
**File:** `src/zebtrack/io/recorder.py`

**New Methods:**
```python
def pause_recording() -> bool
    """Pause recording during disconnect."""

def resume_recording() -> bool
    """Resume recording after reconnect."""

def is_paused() -> bool
    """Check if paused."""

def get_pause_metadata() -> dict
    """Get pause stats for report."""
```

**Behavior:**
- `write_detection_data()` skips if paused
- `write_video_frame()` skips if paused
- Tracks total paused duration

### LiveBatchCoordinator
**File:** `src/zebtrack/coordinators/live_batch_coordinator.py`

**Methods:**
```python
def register_session(experiment_id, video_path, metadata) -> str
    """Register session to batch (group/day/subject_id)."""

def mark_batch_complete(batch_id) -> bool
    """Generate unified report for batch."""

def get_active_batches() -> list[BatchMetadata]
    """Get incomplete batches."""
```

**Batch Detection:**
- Groups sessions by `(group, day, subject_id)` tuple
- Auto-generates unified Excel when marked complete
- Aggregates individual summary files

## UI Dialogs

### CameraDisconnectRecoveryDialog
**File:** `src/zebtrack/ui/dialogs/camera_disconnect_recovery_dialog.py`

**Features:**
- 30s countdown with auto-reconnect
- 3 buttons: Wait | Resume | Stop
- Modal dialog, non-blocking callback
- Progress bar visualization

**Integration:**
```python
# Subscribe to disconnect event
event_bus.subscribe("CAMERA_DISCONNECT_DETECTED", show_recovery_dialog)

def show_recovery_dialog(event_data):
    dialog = CameraDisconnectRecoveryDialog(
        parent=root,
        gap_duration_s=event_data["gap_duration_s"],
        experiment_id=event_data["experiment_id"],
        on_action_callback=handle_user_action,
    )
```

### AquariumDetectionProgressDialog
**File:** `src/zebtrack/ui/dialogs/aquarium_detection_progress_dialog.py`

**Features:**
- Frame counter (0/100)
- Progress bar
- Thumbnail with detected bbox
- Valid/invalid detection counts

**Integration:**
```python
# Show during aquarium detection phase
dialog = AquariumDetectionProgressDialog(
    parent=root,
    experiment_id="exp_001",
    max_frames=100,
)

# Update from LiveCameraService
dialog.update_progress(
    frame_number=50,
    frame_image=frame,
    detected_bbox=(100, 50, 900, 650),
    is_valid=True,
)

# Close on completion
dialog.show_completion(success=True, message="Aquário detectado!")
```

## Testing

### Unit Tests
```bash
# Hardware detection
pytest tests/test_hardware_capability.py -v

# Mode selection
pytest tests/test_live_camera_mode.py -v

# Recorder pause/resume
pytest tests/test_recorder_pause_resume.py -v
```

### Integration Tests
```bash
# End-to-end live workflow
pytest tests/test_live_camera_workflow_e2e.py -v

# Camera disconnect recovery
pytest tests/test_camera_disconnect_recovery.py -v
```

### Manual Testing
```bash
# Test hardware detection
poetry run python -m zebtrack.utils.hardware_capability

# Test mode selection
poetry run python scripts/test_live_camera_modes.py
```

## Common Patterns

### Pattern 1: Wizard Integration
```python
# In LiveConfigStep
def on_aquarium_count_changed(self, count: int):
    # Check hardware
    hardware_report = assess_hardware_for_live_multi_aquarium(self.settings)

    # Get recommendation
    selector = LiveCameraModeSelector(self.settings)
    recommendation = selector.recommend_mode(count, hardware_report)

    if recommendation.warnings:
        # Show warning dialog with alternatives
        self.show_mode_selection_dialog(recommendation)
```

### Pattern 2: Event-Driven Disconnect Recovery
```python
# In UICoordinator.__init__
self.event_bus.subscribe("CAMERA_DISCONNECT_DETECTED", self._on_camera_disconnect)

def _on_camera_disconnect(self, event_data):
    self.root.after(0, lambda: self._show_recovery_dialog(event_data))
```

### Pattern 3: Batch Report Monitoring
```python
# In ProjectViewManager
def on_session_complete(self, experiment_id):
    batch = self.batch_coordinator.get_batch_for_session(experiment_id)
    if batch and batch.session_count >= self.expected_session_count:
        # Last session → trigger unified report
        self.batch_coordinator.mark_batch_complete(batch.batch_id)
```

## Troubleshooting

**Issue:** Hardware detector always returns LIMITED
**Fix:** Check `psutil` installation; verify CPU/RAM detection:
```python
import psutil
print(f"CPU: {psutil.cpu_count()}, RAM: {psutil.virtual_memory().available / 1e9}GB")
```

**Issue:** Recorder doesn't pause on disconnect
**Fix:** Ensure `LiveCameraService._check_camera_disconnect()` is called in capture loop.

**Issue:** Batch reports not generating
**Fix:** Call `batch_coordinator.mark_batch_complete(batch_id)` explicitly after last session.

**Issue:** Multi-aquarium detection uses too much RAM
**Fix:** Reduce `processing_interval_frames` in LiveConfigStep (default 10 → 20).

## References

- ADR-008: Multi-Aquarium Architecture Decision
- `docs/performance/LIVE_CAMERA_BENCHMARKS.md` - Performance metrics
- `tests/test_live_camera_workflow_e2e.py` - End-to-end examples
