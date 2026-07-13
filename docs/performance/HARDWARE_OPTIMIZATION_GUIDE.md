# Hardware Optimization Guide

Guide for optimizing DRerio LogAI performance on different hardware profiles,
from low-end lab computers (4 GB RAM, no GPU) to high-end systems with NPU.

## Automatic Hardware Detection

DRerio LogAI automatically benchmarks your system on first startup and applies
optimal settings. The benchmark caches results so subsequent launches are fast.

To force a re-benchmark, delete the cache:

```bash
Remove-Item -Recurse -Force openvino_model_cache/benchmark_cache.json
```

## Hardware Profiles

### Low-End (4-8 GB RAM, CPU-only, i3/i5)

Typical for Brazilian university labs. DRerio LogAI auto-detects and applies:

| Setting                  | Auto Value | Effect                        |
| ------------------------ | ---------- | ----------------------------- |
| `performance.memory_mode`| `low`      | Reduces peak RAM usage        |
| `openvino.batch_nireq`   | `1`        | Single inference request      |
| `enable_parallel_analysis`| `false`   | Sequential analysis           |
| `yolo_model.inference_size`| `320-416`| Smaller input, faster inference |

**Expected performance**: 5-15 FPS on i5 with OpenVINO, sufficient for
offline video analysis at `analysis_interval_frames: 10` (1 detection per
10 frames).

**Manual override** in `config.yaml`:

```yaml
performance:
  memory_mode: "low"
  auto_inference_size: true
  enable_parallel_analysis: false

openvino:
  batch_nireq: 1
  precision: "FP32"  # INT8 recommended if model exported
```

### Mid-Range (8-16 GB RAM, Intel iGPU)

Typical Intel i5/i7 with Iris Xe integrated graphics.

| Setting                  | Auto Value | Effect                           |
| ------------------------ | ---------- | -------------------------------- |
| `performance.memory_mode`| `normal`   | Full parallelism                 |
| `openvino.device`        | `GPU`/`AUTO`| iGPU often beats CPU           |
| `openvino.precision`     | `FP16`     | iGPU FP16 is faster than FP32   |
| `yolo_model.inference_size`| `640`    | Full resolution                  |

### High-End (16+ GB RAM, Intel Core Ultra with NPU)

| Setting                  | Auto Value | Effect                     |
| ------------------------ | ---------- | -------------------------- |
| `openvino.device`        | `NPU`/`AUTO`| NPU frees CPU for UI     |
| `openvino.precision`     | `FP16`     | NPU native precision       |
| `yolo_model.inference_size`| `640`    | Full resolution            |

See [NPU_SETUP_GUIDE.md](NPU_SETUP_GUIDE.md) for detailed NPU configuration.

## INT8 Quantization

INT8 provides 2-4x speedup on CPU with less than 1% accuracy loss.
Particularly beneficial for low-end systems.

### Exporting an INT8 Model

INT8 export uses Ultralytics built-in quantization with NNCF:

```python
from zebtrack.core.services.weight_manager import WeightManager
wm = WeightManager(config_dir=".")
wm.convert_to_openvino_int8("best_oi")  # Exports to openvino_model_cache/
```

The export takes 2-5 minutes (calibration step). The resulting model
is stored alongside the standard FP16 model:

```text
openvino_model_cache/
├── best_oi_openvino_model/      # FP16 (standard)
└── best_oi_openvino_int8_model/ # INT8 (quantized)
```

### Using INT8 at Runtime

Set the precision in `config.yaml`:

```yaml
openvino:
  precision: "INT8"
```

The OpenVINO detector applies the `INFERENCE_PRECISION_HINT` to use INT8
operations where the model supports them.

## Inference Size Tuning

The YOLO model input size directly impacts speed and accuracy:

| Size | Relative Speed | Accuracy Impact | Recommended For         |
| ---- | -------------- | --------------- | ----------------------- |
| 640  | 1.0x (baseline)| Best            | GPU systems, NPU        |
| 416  | ~1.4x          | Minimal         | Mid-range CPU           |
| 320  | ~1.75x         | Slight decrease | Low-end CPU, 4 GB RAM   |

When `auto_inference_size: true` (default), the benchmark selects the
optimal size automatically. To override:

```yaml
performance:
  auto_inference_size: false  # Disable auto-selection

yolo_model:
  inference_size: 416  # Manual override
```

## Memory Mode Details

### Normal Mode (default)

- `batch_nireq: 4` — overlaps preprocessing with inference
- `enable_parallel_analysis: true` — concurrent analysis components
- Suitable for 8+ GB RAM systems

### Low Mode (auto-detected for < 8 GB RAM)

- `batch_nireq: 1` — single inference request (saves ~200 MB)
- `enable_parallel_analysis: false` — sequential analysis
- Reduces peak RAM by approximately 30-40%

## Benchmark Interpretation

After running, check the benchmark summary:

```bash
poetry run python -c "
from zebtrack.utils.hardware_benchmark import load_cached_benchmark, print_benchmark_summary
result = load_cached_benchmark()
if result:
    print_benchmark_summary(result)
"
```

Key metrics:

- **Estimated FPS (live)**: Should be > 10 for real-time tracking
- **Estimated FPS (batch)**: Higher is better for offline processing
- **Recommended device**: The benchmark's optimal device selection
- **Recommended inference size**: Auto-selected based on hardware
- **Recommended memory mode**: `normal` or `low` based on RAM
