# Intel NPU Setup Guide

Guide for configuring ZebTrack-AI to use Intel Neural Processing Units (NPU)
for hardware-accelerated zebrafish tracking inference.

## Requirements

- **CPU**: Intel Core Ultra (Meteor Lake or newer) with integrated NPU
- **Driver**: Intel NPU driver installed and up-to-date
- **OpenVINO**: Version 2026.0+ (bundled with ZebTrack-AI)
- **OS**: Windows 11 (23H2+) or Linux with NPU kernel module

## Verifying NPU Availability

Run the hardware summary to check if your NPU is detected:

```bash
poetry run python -c "
from zebtrack.utils.hardware_detection import get_hardware_summary
summary = get_hardware_summary()
print(f'NPU available: {summary[\"has_npu\"]}')
print(f'OpenVINO devices: {summary[\"openvino_devices\"]}')
"
```

Expected output on a Core Ultra system:

```text
NPU available: True
OpenVINO devices: ['CPU', 'GPU', 'NPU']
```

## Configuration

### Automatic (Recommended)

ZebTrack-AI auto-detects NPU during the first-run benchmark.
If NPU is available, it appears in the device selection combobox
in the Calibration Dialog (Global Settings).

The `AUTO` device mode (default) lets OpenVINO choose the best
device automatically, which may include NPU scheduling.

### Manual Device Selection

#### Via GUI

1. Open **Global Settings** (Calibration Dialog)
2. Enable **OpenVINO** checkbox
3. Select **NPU** from the device dropdown
4. The setting applies immediately

#### Via config.yaml

```yaml
openvino:
  device: "NPU"       # Force NPU for live camera
  device_batch: "CPU"  # Keep CPU for offline batch (recommended)
  npu_turbo: false     # Enable for short burst workloads
```

## NPU Turbo Mode

Turbo mode increases NPU clock speed for higher throughput at the
cost of extra power consumption. Only useful for short-duration
tasks (model diagnostics, single-frame analysis).

```yaml
openvino:
  npu_turbo: true  # Not recommended for sustained tracking
```

## Performance Characteristics

| Metric          | NPU        | CPU (i7)   | iGPU (Iris Xe) |
| --------------- | ---------- | ---------- | --------------- |
| FP16 Latency    | ~8-12 ms   | ~15-25 ms  | ~10-18 ms       |
| Power Draw      | ~5-10 W    | ~15-45 W   | ~10-25 W        |
| Thermal Impact  | Minimal    | Moderate   | Low-Moderate    |
| Best For        | Live/batch | Batch only | Live analysis   |

NPU advantages:

- Frees CPU for preprocessing and UI while inference runs on NPU
- Very low power consumption for sustained workloads
- Native FP16 precision (no accuracy loss vs FP32 for YOLO)

## Troubleshooting

### NPU Not Detected

1. Check Windows Device Manager for "Intel AI Boost" (NPU device)
2. Update Intel NPU driver from Intel Driver & Support Assistant
3. Verify with: `poetry run python -c "import openvino as ov; print(ov.Core().available_devices)"`

### NPU Inference Errors

If NPU compilation fails, ZebTrack-AI automatically falls back to
CPU. Check logs for:

```text
openvino_detector.npu_compile.failed
openvino_detector.fallback_to_cpu
```

Common causes:

- Unsupported model operations (rare with YOLO)
- Driver version mismatch (update driver)
- Model not in FP16 format (re-export with `half=True`)

### Cache Issues

Clear the compiled model cache if NPU behavior changes after
a driver update:

```bash
# Remove compiled cache (not the model IR files)
Remove-Item -Recurse -Force openvino_model_cache/compiled_cache
```
