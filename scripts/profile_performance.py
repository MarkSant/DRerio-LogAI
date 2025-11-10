#!/usr/bin/env python3
"""
Performance Profiling Script for ZebTrack-AI

This script provides comprehensive performance profiling capabilities:
- CPU profiling (cProfile)
- Memory profiling (tracemalloc)
- Live monitoring (continuous sampling)

Usage:
    # CPU profiling
    poetry run python scripts/profile_performance.py --mode cpu --function detect

    # Memory profiling
    poetry run python scripts/profile_performance.py --mode memory --function process_video

    # Live monitoring
    poetry run python scripts/profile_performance.py --mode live --duration 60

    # Full suite
    poetry run python scripts/profile_performance.py --mode all
"""

import argparse
import cProfile
import gc
import io
import platform
import pstats
import resource
import sys
import time
import tracemalloc
from contextlib import contextmanager
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Optional structlog for logging
try:
    import structlog
    log = structlog.get_logger(__name__)
except ImportError:
    class DummyLogger:
        def info(self, *args, **kwargs):
            pass
        def error(self, *args, **kwargs):
            pass
    log = DummyLogger()


class PerformanceProfiler:
    """Main profiler class for ZebTrack-AI performance analysis."""

    def __init__(self, output_dir: Path | None = None):
        """Initialize profiler.

        Args:
            output_dir: Directory to save profiling results. Defaults to ./profiling_results/
        """
        self.output_dir = output_dir or Path("profiling_results")
        self.output_dir.mkdir(exist_ok=True)

    # -------------------------------------------------------------------------
    # CPU Profiling
    # -------------------------------------------------------------------------

    @contextmanager
    def cpu_profile(self, name: str = "profile"):
        """Context manager for CPU profiling with cProfile.

        Args:
            name: Name for the profile output file

        Example:
            with profiler.cpu_profile("detector"):
                # ... code to profile ...
        """
        profiler = cProfile.Profile()
        profiler.enable()

        try:
            yield profiler
        finally:
            profiler.disable()
            self._save_cpu_profile(profiler, name)

    def _save_cpu_profile(self, profiler: cProfile.Profile, name: str):
        """Save CPU profiling results to file and print summary."""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        output_file = self.output_dir / f"cpu_{name}_{timestamp}.prof"

        # Save binary profile
        profiler.dump_stats(str(output_file))
        log.info(
            "profiler.cpu.saved",
            output_file=str(output_file),
        )

        # Print summary to stdout
        s = io.StringIO()
        ps = pstats.Stats(profiler, stream=s)
        ps.strip_dirs()
        ps.sort_stats("cumulative")
        ps.print_stats(30)  # Top 30 functions

        print("\n" + "=" * 80)
        print(f"CPU PROFILE: {name}")
        print("=" * 80)
        print(s.getvalue())
        print("=" * 80 + "\n")

        # Also save text summary
        text_file = self.output_dir / f"cpu_{name}_{timestamp}.txt"
        with open(text_file, "w") as f:
            f.write(s.getvalue())

        log.info(
            "profiler.cpu.summary_saved",
            text_file=str(text_file),
        )

    # -------------------------------------------------------------------------
    # Memory Profiling
    # -------------------------------------------------------------------------

    @contextmanager
    def memory_profile(self, name: str = "memory"):
        """Context manager for memory profiling with tracemalloc.

        Args:
            name: Name for the profile output file

        Example:
            with profiler.memory_profile("recorder"):
                # ... code to profile ...
        """
        tracemalloc.start()
        snapshot_before = tracemalloc.take_snapshot()

        try:
            yield
        finally:
            snapshot_after = tracemalloc.take_snapshot()
            self._save_memory_profile(snapshot_before, snapshot_after, name)
            if tracemalloc.is_tracing():
                tracemalloc.stop()

    def _save_memory_profile(
        self,
        snapshot_before: tracemalloc.Snapshot,
        snapshot_after: tracemalloc.Snapshot,
        name: str,
    ):
        """Save memory profiling results."""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        output_file = self.output_dir / f"memory_{name}_{timestamp}.txt"

        top_stats = snapshot_after.compare_to(snapshot_before, "lineno")

        with open(output_file, "w") as f:
            f.write("=" * 80 + "\n")
            f.write(f"MEMORY PROFILE: {name}\n")
            f.write("=" * 80 + "\n\n")
            f.write("Top 30 memory allocations:\n\n")

            for stat in top_stats[:30]:
                f.write(f"{stat}\n")

            # Summary statistics
            current, peak = tracemalloc.get_traced_memory()
            f.write("\n" + "=" * 80 + "\n")
            f.write(f"Current memory usage: {current / 1024 / 1024:.2f} MB\n")
            f.write(f"Peak memory usage: {peak / 1024 / 1024:.2f} MB\n")
            f.write("=" * 80 + "\n")

        print("\n" + "=" * 80)
        print(f"MEMORY PROFILE: {name}")
        print("=" * 80)
        print(f"Current memory usage: {current / 1024 / 1024:.2f} MB")
        print(f"Peak memory usage: {peak / 1024 / 1024:.2f} MB")
        print(f"Results saved to: {output_file}")
        print("=" * 80 + "\n")

        log.info(
            "profiler.memory.saved",
            output_file=str(output_file),
            current_mb=current / 1024 / 1024,
            peak_mb=peak / 1024 / 1024,
        )

    # -------------------------------------------------------------------------
    # Live Monitoring (using resource module instead of psutil)
    # -------------------------------------------------------------------------

    def live_monitor(self, duration: int = 60, interval: float = 1.0):
        """Monitor system resources in real-time using resource module.

        Args:
            duration: Monitoring duration in seconds
            interval: Sampling interval in seconds
        """
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        output_file = self.output_dir / f"live_monitor_{timestamp}.csv"

        print(f"\n{'=' * 80}")
        print(f"LIVE MONITORING (duration={duration}s, interval={interval}s)")
        print(f"{'=' * 80}\n")
        print("Note: Using resource module for memory tracking")
        print()

        samples = []
        start_time = time.time()

        with open(output_file, "w") as f:
            # CSV header
            f.write("timestamp,memory_mb,gc_collections\n")

            while time.time() - start_time < duration:
                # Sample metrics using resource module
                usage = resource.getrusage(resource.RUSAGE_SELF)
                # Adjust for platform differences in ru_maxrss
                if platform.system() == "Darwin":  # macOS
                    mem_mb = usage.ru_maxrss / 1024 / 1024  # bytes to MB
                else:  # Linux
                    mem_mb = usage.ru_maxrss / 1024  # KB to MB
                gc_count = sum(gc.get_count())

                sample = {
                    "timestamp": time.time() - start_time,
                    "memory_mb": mem_mb,
                    "gc_collections": gc_count,
                }
                samples.append(sample)

                # Write to CSV
                f.write(
                    f"{sample['timestamp']:.2f},"
                    f"{sample['memory_mb']:.2f},"
                    f"{sample['gc_collections']}\n"
                )
                f.flush()  # Ensure data is written immediately for real-time monitoring

                # Print progress
                print(
                    f"[{sample['timestamp']:6.1f}s] "
                    f"MEM: {mem_mb:7.1f}MB | "
                    f"GC: {gc_count}",
                    end="\r",
                )

                time.sleep(interval)

        print(f"\n\n{'=' * 80}")
        print("LIVE MONITORING SUMMARY")
        print(f"{'=' * 80}")
        print(f"Samples collected: {len(samples)}")
        print(f"Results saved to: {output_file}")

        if samples:
            avg_mem = sum(s["memory_mb"] for s in samples) / len(samples)
            max_mem = max(s["memory_mb"] for s in samples)

            print(f"Average Memory: {avg_mem:.2f} MB")
            print(f"Peak Memory: {max_mem:.2f} MB")

        print(f"{'=' * 80}\n")

        log.info(
            "profiler.live_monitor.completed",
            output_file=str(output_file),
            samples=len(samples),
        )

    # -------------------------------------------------------------------------
    # Benchmark Functions
    # -------------------------------------------------------------------------

    def benchmark_detector_initialization(self):
        """Benchmark detector initialization time."""
        print("\n" + "=" * 80)
        print("BENCHMARK: Detector Initialization")
        print("=" * 80 + "\n")

        try:
            from zebtrack.settings import load_settings
            from zebtrack.core.detector import Detector
            from zebtrack.plugins import DETECTOR_PLUGINS

            settings = load_settings()
            
            # Use configured model path from settings
            model_path = settings.detector.model_path
            
            # Fallback to cache location if not set
            if not model_path or not Path(model_path).exists():
                cache_path = Path.home() / ".cache" / "zebtrack" / "yolo11n.pt"
                if cache_path.exists():
                    model_path = str(cache_path)
                else:
                    print(f"SKIPPED: Model not found at {cache_path}\n")
                    return None

            with self.cpu_profile("detector_init"):
                start = time.time()
                detector = Detector(
                    detector_name="yolo",
                    model_path=model_path,
                    detector_plugins=DETECTOR_PLUGINS,
                    settings_obj=settings,
                )
                elapsed = time.time() - start

            print(f"Detector initialization took: {elapsed:.3f}s\n")
            return detector
        except Exception as e:
            print(f"SKIPPED: Cannot initialize detector: {e}\n")
            return None

    def benchmark_frame_detection(self, detector, num_frames: int = 100):
        """Benchmark frame detection performance.

        Args:
            detector: Initialized Detector instance
            num_frames: Number of synthetic frames to process
        """
        if detector is None:
            print("\n" + "=" * 80)
            print(f"BENCHMARK: Frame Detection ({num_frames} frames)")
            print("=" * 80 + "\n")
            print("SKIPPED: No detector available\n")
            return

        print("\n" + "=" * 80)
        print(f"BENCHMARK: Frame Detection ({num_frames} frames)")
        print("=" * 80 + "\n")

        import numpy as np

        # Create synthetic test frames (640x480 RGB)
        test_frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)

        with self.cpu_profile("frame_detection"):
            with self.memory_profile("frame_detection"):
                start = time.time()
                for i in range(num_frames):
                    detections = detector.detect(test_frame)
                    if i % 10 == 0:
                        print(f"Processed {i}/{num_frames} frames...", end="\r")
                elapsed = time.time() - start

        fps = num_frames / elapsed
        print(f"\nFrame detection completed:")
        print(f"  Total time: {elapsed:.3f}s")
        print(f"  FPS: {fps:.2f}")
        print(f"  Avg time per frame: {elapsed/num_frames*1000:.2f}ms\n")

    def benchmark_parquet_write(self, num_rows: int = 10000):
        """Benchmark Parquet write performance.

        Args:
            num_rows: Number of rows to write
        """
        print("\n" + "=" * 80)
        print(f"BENCHMARK: Parquet Write ({num_rows} rows)")
        print("=" * 80 + "\n")

        import numpy as np
        import pandas as pd
        import pyarrow as pa
        import pyarrow.parquet as pq

        # Create synthetic trajectory data
        data = {
            "timestamp": np.arange(num_rows, dtype=np.float64),
            "frame": np.arange(num_rows, dtype=np.int32),
            "track_id": np.random.randint(0, 10, num_rows, dtype=np.int32),
            "x1": np.random.rand(num_rows) * 640,
            "y1": np.random.rand(num_rows) * 480,
            "x2": np.random.rand(num_rows) * 640,
            "y2": np.random.rand(num_rows) * 480,
            "confidence": np.random.rand(num_rows),
        }
        df = pd.DataFrame(data)
        table = pa.Table.from_pandas(df)

        # Test different compression codecs
        for compression in ["snappy", "gzip", "none"]:
            output_file = self.output_dir / f"test_{compression}.parquet"

            start = time.time()
            pq.write_table(table, str(output_file), compression=compression)
            write_time = time.time() - start

            file_size = output_file.stat().st_size / 1024 / 1024  # MB

            start = time.time()
            _ = pq.read_table(str(output_file))
            read_time = time.time() - start

            print(f"{compression:8s}: "
                  f"Write={write_time*1000:6.2f}ms, "
                  f"Read={read_time*1000:6.2f}ms, "
                  f"Size={file_size:6.2f}MB")

            output_file.unlink()

        print()

    def benchmark_plot_generation(self):
        """Benchmark matplotlib plot generation."""
        print("\n" + "=" * 80)
        print("BENCHMARK: Plot Generation")
        print("=" * 80 + "\n")

        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np

        # Generate synthetic trajectory data
        num_points = 10000
        x = np.cumsum(np.random.randn(num_points))
        y = np.cumsum(np.random.randn(num_points))

        with self.cpu_profile("plot_generation"):
            with self.memory_profile("plot_generation"):
                start = time.time()

                # Create 5 different plot types (similar to Reporter)
                for i, plot_type in enumerate([
                    "trajectory", "heatmap", "position_vs_time",
                    "cumulative_distance", "angular_velocity"
                ]):
                    fig, ax = plt.subplots(figsize=(10, 6))

                    if plot_type == "trajectory":
                        ax.plot(x, y, alpha=0.7)
                    elif plot_type == "heatmap":
                        ax.hist2d(x, y, bins=50)
                    elif plot_type == "position_vs_time":
                        ax.plot(np.arange(num_points), x)
                        ax.plot(np.arange(num_points), y)
                    elif plot_type == "cumulative_distance":
                        dist = np.cumsum(np.sqrt(np.diff(x)**2 + np.diff(y)**2))
                        ax.plot(dist)
                    else:  # angular_velocity
                        angles = np.arctan2(np.diff(y), np.diff(x))
                        ax.plot(angles)

                    plot_file = self.output_dir / f"test_{plot_type}.png"
                    fig.savefig(str(plot_file), dpi=100, bbox_inches="tight")
                    plt.close(fig)

                    print(f"Generated {i+1}/5 plots...", end="\r")

                elapsed = time.time() - start

        print(f"\nPlot generation completed:")
        print(f"  Total time: {elapsed:.3f}s")
        print(f"  Avg time per plot: {elapsed/5:.3f}s\n")

        # Clean up test plots
        for plot_type in ["trajectory", "heatmap", "position_vs_time",
                          "cumulative_distance", "angular_velocity"]:
            (self.output_dir / f"test_{plot_type}.png").unlink(missing_ok=True)


def main():
    """Main entry point for profiling script."""
    parser = argparse.ArgumentParser(
        description="Performance profiling for ZebTrack-AI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--mode",
        choices=["cpu", "memory", "live", "benchmark", "all"],
        default="benchmark",
        help="Profiling mode (default: benchmark)",
    )

    parser.add_argument(
        "--duration",
        type=int,
        default=60,
        help="Duration for live monitoring in seconds (default: 60)",
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("profiling_results"),
        help="Output directory for profiling results",
    )

    args = parser.parse_args()

    profiler = PerformanceProfiler(output_dir=args.output_dir)

    print("\n" + "=" * 80)
    print("ZebTrack-AI Performance Profiling")
    print("=" * 80)
    print(f"Mode: {args.mode}")
    print(f"Output directory: {args.output_dir}")
    print("=" * 80 + "\n")

    if args.mode == "cpu":
        # CPU profiling mode - detector initialization and frame detection
        detector = profiler.benchmark_detector_initialization()
        if detector:
            profiler.benchmark_frame_detection(detector, num_frames=100)
    
    elif args.mode == "memory":
        # Memory profiling mode - focus on memory-intensive operations
        detector = profiler.benchmark_detector_initialization()
        if detector:
            profiler.benchmark_frame_detection(detector, num_frames=50)
        profiler.benchmark_parquet_write(num_rows=50000)
    
    elif args.mode == "live":
        # Live monitoring mode
        profiler.live_monitor(duration=args.duration)
    
    elif args.mode == "benchmark":
        # Quick benchmark mode - skips slow frame detection by default
        # Frame detection can take 8-10 seconds and is the #1 bottleneck
        # Use --mode cpu to profile detector performance specifically
        detector = profiler.benchmark_detector_initialization()
        profiler.benchmark_parquet_write(num_rows=50000)
        profiler.benchmark_plot_generation()
    
    elif args.mode == "all":
        # Comprehensive profiling - all benchmarks + live monitoring
        detector = profiler.benchmark_detector_initialization()
        if detector:
            profiler.benchmark_frame_detection(detector, num_frames=100)
        profiler.benchmark_parquet_write(num_rows=50000)
        profiler.benchmark_plot_generation()
        profiler.live_monitor(duration=30)

    print("\n" + "=" * 80)
    print("Profiling Complete!")
    print(f"Results saved to: {args.output_dir}")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
