# Performance Tuning & Troubleshooting

**Category:** Guide (Diátaxis)
**Status:** Canonical

## 1. Configuring Performance

Performance settings are controlled via the `performance` section in `config.yaml`.

```yaml
performance:
  max_parallel_plots: 3 # Number of threads for report generation
  parquet_compression: "snappy" # options: snappy, gzip, none
  video_prefetch_frames: 30 # Buffer for video decoding
```

## 2. Troubleshooting Common Issues

### 2.1. High Memory Usage during Reporting

If the application crashes during the "Generating Reports" step:

1. **Reduce Parallelism:** Set `max_parallel_plots: 1` in your `config.local.yaml`.
2. **Check Memory Leak:** Monitor `python.exe` memory usage. If it exceeds 2GB, check if large video files are being loaded entirely into memory (they shouldn't be).

### 2.2. Plots are Empty or Corrupted

1. **Backend Conflict:** Ensure `matplotlib.get_backend()` returns `Agg`.
2. **Concurrency Race:** If two threads attempt to modify the same global Matplotlib state, plots may fail. The system uses independent figure objects to avoid this, but some plugins may interfere.

### 2.3. Parquet Read Failures

If external scripts (R/Python) cannot read the tracking data:

1. **Library Sync:** Ensure you are using `pyarrow` or `fastparquet` v1.0+.
2. **Compression Support:** If using an environment without Snappy support, switch `parquet_compression` to `none`.

## 3. Profiling Tools

To diagnose specific performance degradation, use the following:

- **cProfile:** `python -m cProfile -o profile.out -m zebtrack`
- **Memory Profiler:** Requires `@profile` decorator on suspected methods.
- **Benchmark Scripts:** Located in `debug/` (e.g., `debug/benchmark_full_system.py`).
