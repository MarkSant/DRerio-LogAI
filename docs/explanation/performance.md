# Performance Architecture & Baselines

**Category:** Explanation (Diátaxis)
**Status:** Canonical

## 1. System Baselines (Target vs. Actual)

These metrics represent the performance characteristics of DRerio LogAI on standard lab hardware (e.g., Intel i7-12th Gen).

| Metric              | Baseline    | Target    | Bottleneck                         |
| ------------------- | ----------- | --------- | ---------------------------------- |
| **Detection FPS**   | 12-18 (CPU) | 30+       | YOLO inference latency             |
| **OpenVINO FPS**    | 22-30       | 60+ (GPU) | Weight conversion overhead         |
| **Plot Generation** | 3s per plot | <1s       | Matplotlib single-threaded backend |
| **Parquet Write**   | <50ms/batch | -         | I/O contention (avoided by Snappy) |

### 1.1. Extended Baseline Snapshot (Nov 2025)

Archived benchmarks add context for memory and end-to-end latency on CPU-only runs:

| Metric                       | Observed    | Notes                               |
| ---------------------------- | ----------- | ----------------------------------- |
| **Detection FPS (CPU)**      | 8-12 FPS    | 640×480, YOLO11n, CPU inference     |
| **End-to-end (5 min video)** | ~14-15 min  | Detection dominates total time      |
| **Peak memory**              | ~1.0-1.2 GB | Detector + buffers + parallel plots |

Use these numbers as a baseline when validating regressions or hardware changes.

## 2. Concurrency Model

DRerio LogAI uses a multi-threaded approach to keep the UI responsive during intensive tasks.

### 2.1. Threaded Components

- **LiveCameraService:** Captures frames from hardware. Uses a dedicated daemon thread.
- **ProcessingWorker:** Executes the detection loop. Communicates state via the `StateManager`.
- **Reporter (Plots):** Uses a `ThreadPoolExecutor` to generate scientific plots in parallel (up to 3-5 workers).

### 2.2. Thread Safety Mechanisms

- **StateManager:** Uses `RLock` and deferred observer notifications to prevent deadlocks.
- **Tkinter root.after:** All UI updates from background threads must be scheduled via `root.after(0, ...)` to ensure they run on the main thread.

## 3. Storage Efficiency

Tracking results are stored in **Apache Parquet** format.

- **Snappy Compression:** Provides a 60% reduction in file size compared to CSV/JSON with negligible CPU overhead.
- **Batch Flush:** Data is buffered in memory and flushed periodically to disk to minimize I/O interrupts.

---

**See also:** For troubleshooting information, refer to the [Performance Tuning Guide](../guides/developer/performance-tuning.md).
