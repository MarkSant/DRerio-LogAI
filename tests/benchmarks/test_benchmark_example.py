"""
Benchmark tests for performance-critical components.

These tests measure execution time using pytest-benchmark.
Run with: poetry run pytest tests/benchmarks/ -n0 --benchmark-only

The -n0 flag is required because pytest-benchmark cannot run in parallel mode.
"""

import numpy as np
import pytest


@pytest.mark.benchmark
def test_benchmark_numpy_operations(benchmark):
    """Benchmark example: numpy array operations."""

    def numpy_computation():
        arr = np.random.rand(1000, 1000)
        return arr.mean()

    result = benchmark(numpy_computation)
    assert result is not None


@pytest.mark.benchmark
def test_benchmark_list_comprehension(benchmark):
    """Benchmark example: Python list comprehension."""

    def list_comp():
        return [x**2 for x in range(10000)]

    result = benchmark(list_comp)
    assert len(result) == 10000


@pytest.mark.benchmark
def test_benchmark_frame_preprocessing(benchmark):
    """Benchmark frame preprocessing operations."""
    # Create sample frame
    frame = np.random.randint(0, 255, (640, 480, 3), dtype=np.uint8)

    def preprocess_frame():
        # Simulate preprocessing (resize, normalize, etc.)
        resized = frame[::2, ::2, :]  # Simple downsampling
        normalized = resized.astype(np.float32) / 255.0
        return normalized

    result = benchmark(preprocess_frame)
    assert result.shape[0] < frame.shape[0]
    assert result.dtype == np.float32
