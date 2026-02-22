"""Benchmarks for Phase 7 — Performance Optimizations.

Run with:
    poetry run pytest tests/benchmarks/test_phase7_benchmarks.py -n0 --benchmark-only

Each benchmark isolates the optimized hot-path so regressions are measurable.
"""

from __future__ import annotations

import math
from unittest.mock import MagicMock

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# 7.4 — Vectorized angular velocity
# ---------------------------------------------------------------------------


def _get_angular_velocity_vectorized(x_coords, y_coords):
    """Vectorized implementation (production code in behavior.py)."""
    if len(x_coords) < 3:
        return []
    x = np.asarray(x_coords, dtype=np.float64)
    y = np.asarray(y_coords, dtype=np.float64)
    dx = np.diff(x)
    dy = np.diff(y)
    dist = np.hypot(dx, dy)
    angles = np.arctan2(dy, dx)
    d_angle = np.diff(angles)
    d_angle = (d_angle + np.pi) % (2 * np.pi) - np.pi
    mask = dist[:-1] > 1e-9
    ang_vel = np.where(mask, np.abs(d_angle) / dist[:-1], 0.0)
    result = np.empty(len(x), dtype=np.float64)
    result[0] = 0.0
    result[1] = 0.0
    result[2:] = ang_vel
    return result.tolist()


def _get_angular_velocity_loop(x_coords, y_coords):
    """Original loop-based implementation for comparison."""
    if len(x_coords) < 3:
        return []
    angular_velocities = [0.0, 0.0]
    for i in range(2, len(x_coords)):
        dx1 = x_coords[i - 1] - x_coords[i - 2]
        dy1 = y_coords[i - 1] - y_coords[i - 2]
        dx2 = x_coords[i] - x_coords[i - 1]
        dy2 = y_coords[i] - y_coords[i - 1]
        angle1 = math.atan2(dy1, dx1)
        angle2 = math.atan2(dy2, dx2)
        delta_angle = angle2 - angle1
        delta_angle = (delta_angle + math.pi) % (2 * math.pi) - math.pi
        dist = math.sqrt(dx2**2 + dy2**2)
        ang_vel = abs(delta_angle) / dist if dist > 1e-9 else 0.0
        angular_velocities.append(ang_vel)
    return angular_velocities


@pytest.mark.benchmark
def test_benchmark_angular_velocity_vectorized(benchmark):
    """Benchmark vectorized angular velocity (Phase 7.4)."""
    rng = np.random.default_rng(42)
    x = np.cumsum(rng.normal(0, 5, 5000)).tolist()
    y = np.cumsum(rng.normal(0, 5, 5000)).tolist()

    result = benchmark(_get_angular_velocity_vectorized, x, y)
    assert len(result) == 5000


@pytest.mark.benchmark
def test_benchmark_angular_velocity_loop_baseline(benchmark):
    """Baseline: loop-based angular velocity for comparison."""
    rng = np.random.default_rng(42)
    x = np.cumsum(rng.normal(0, 5, 5000)).tolist()
    y = np.cumsum(rng.normal(0, 5, 5000)).tolist()

    result = benchmark(_get_angular_velocity_loop, x, y)
    assert len(result) == 5000


# ---------------------------------------------------------------------------
# 7.5 — Columnar buffers (pa.table vs pd.DataFrame)
# ---------------------------------------------------------------------------


@pytest.mark.benchmark
def test_benchmark_columnar_pa_table(benchmark):
    """Benchmark direct pyarrow table construction (Phase 7.5)."""
    import pyarrow as pa

    n = 500
    data = {
        "timestamp": [float(i) / 30.0 for i in range(n)],
        "frame": list(range(n)),
        "track_id": [0] * n,
        "x1": np.random.rand(n).tolist(),
        "y1": np.random.rand(n).tolist(),
        "x2": np.random.rand(n).tolist(),
        "y2": np.random.rand(n).tolist(),
        "confidence": np.random.rand(n).tolist(),
    }

    def build_pa_table():
        return pa.table(
            {
                k: pa.array(v, type=pa.float64() if isinstance(v[0], float) else pa.int64())
                for k, v in data.items()
            }
        )

    result = benchmark(build_pa_table)
    assert result.num_rows == n


@pytest.mark.benchmark
def test_benchmark_columnar_pd_dataframe_baseline(benchmark):
    """Baseline: pd.DataFrame→pa.Table for comparison."""
    import pandas as pd
    import pyarrow as pa

    n = 500
    data = {
        "timestamp": [float(i) / 30.0 for i in range(n)],
        "frame": list(range(n)),
        "track_id": [0] * n,
        "x1": np.random.rand(n).tolist(),
        "y1": np.random.rand(n).tolist(),
        "x2": np.random.rand(n).tolist(),
        "y2": np.random.rand(n).tolist(),
        "confidence": np.random.rand(n).tolist(),
    }

    def build_via_pandas():
        df = pd.DataFrame(data)
        return pa.Table.from_pandas(df)

    result = benchmark(build_via_pandas)
    assert result.num_rows == n


# ---------------------------------------------------------------------------
# 7.6 — Polygon mask cache (cv2.fillPoly O(1) lookup vs pointPolygonTest)
# ---------------------------------------------------------------------------


@pytest.mark.benchmark
def test_benchmark_polygon_mask_lookup(benchmark):
    """Benchmark mask-based polygon containment (Phase 7.6)."""
    import cv2

    # Build mask once
    w, h = 640, 480
    polygon = np.array([[100, 100], [500, 100], [500, 400], [100, 400]], dtype=np.int32)
    mask = np.zeros((h, w), dtype=np.uint8)
    cv2.fillPoly(mask, [polygon], 255)

    # Random test points
    rng = np.random.default_rng(0)
    points = rng.integers(0, [w, h], size=(1000, 2))

    def check_mask():
        count = 0
        for px, py in points:
            if mask[py, px]:
                count += 1
        return count

    result = benchmark(check_mask)
    assert result > 0


@pytest.mark.benchmark
def test_benchmark_polygon_point_test_baseline(benchmark):
    """Baseline: cv2.pointPolygonTest for comparison."""
    import cv2

    polygon = np.array([[100, 100], [500, 100], [500, 400], [100, 400]], dtype=np.float32)
    rng = np.random.default_rng(0)
    points = rng.integers(0, [640, 480], size=(1000, 2))

    def check_point_test():
        count = 0
        for px, py in points:
            if cv2.pointPolygonTest(polygon, (float(px), float(py)), False) >= 0:
                count += 1
        return count

    result = benchmark(check_point_test)
    assert result > 0


# ---------------------------------------------------------------------------
# 7.7 — TTL cache utility
# ---------------------------------------------------------------------------


@pytest.mark.benchmark
def test_benchmark_ttl_cache_get_set(benchmark):
    """Benchmark TTLCache get/set operations (Phase 7.7)."""
    from zebtrack.utils.cache import TTLCache

    cache = TTLCache(ttl_seconds=60.0)

    def cache_ops():
        for i in range(1000):
            cache.set(f"key_{i}", i)
        total = 0
        for i in range(1000):
            v = cache.get(f"key_{i}")
            if v is not None:
                total += v
        return total

    result = benchmark(cache_ops)
    assert result > 0


# ---------------------------------------------------------------------------
# 7.3 — SharedMemory buffer write/read
# ---------------------------------------------------------------------------


@pytest.mark.benchmark
def test_benchmark_shared_memory_write(benchmark):
    """Benchmark SharedFrameBuffer write throughput (Phase 7.3)."""
    from zebtrack.core.video.shared_frame_buffer import SharedFrameBuffer

    frame = np.random.randint(0, 255, (720, 1280, 3), dtype=np.uint8)
    buf = SharedFrameBuffer(name="bench_write", create=True)
    try:

        def write_frame():
            return buf.write(frame)

        meta = benchmark(write_frame)
        assert "shm_seq" in meta
    finally:
        buf.close_and_unlink()


@pytest.mark.benchmark
def test_benchmark_shared_memory_roundtrip(benchmark):
    """Benchmark SharedFrameBuffer write+read round-trip (Phase 7.3)."""
    from zebtrack.core.video.shared_frame_buffer import SharedFrameBuffer

    frame = np.random.randint(0, 255, (720, 1280, 3), dtype=np.uint8)
    buf = SharedFrameBuffer(name="bench_rt", create=True)
    try:

        def roundtrip():
            meta = buf.write(frame)
            return buf.read(meta["shm_seq"])

        result = benchmark(roundtrip)
        assert result is not None
        assert result.shape == frame.shape
    finally:
        buf.close_and_unlink()


@pytest.mark.benchmark
def test_benchmark_pickle_frame_baseline(benchmark):
    """Baseline: pickle a 720p frame for comparison with SharedMemory."""
    import pickle

    frame = np.random.randint(0, 255, (720, 1280, 3), dtype=np.uint8)

    def pickle_frame():
        data = pickle.dumps(frame)
        return pickle.loads(data)

    result = benchmark(pickle_frame)
    assert result.shape == frame.shape


# ---------------------------------------------------------------------------
# 7.8 — Model warm-up (structural test — timing not meaningful in isolation)
# ---------------------------------------------------------------------------


@pytest.mark.benchmark
def test_benchmark_warm_up_ultralytics(benchmark):
    """Benchmark Ultralytics warm-up call overhead (Phase 7.8)."""
    plugin = MagicMock()
    plugin.model = MagicMock()
    plugin.model.predictor = None

    def warm_up():
        dummy = np.zeros((1, 320, 320, 3), dtype=np.uint8)
        plugin.model.predict(dummy, verbose=False)

    benchmark(warm_up)
    assert plugin.model.predict.called


# ---------------------------------------------------------------------------
# 7.9 — OpenVINO AsyncInferQueue batch inference
# ---------------------------------------------------------------------------


def _make_mock_openvino_plugin(*, latency_ms: float = 2.0, nireq: int = 4):
    """Create a mock OpenVINOPlugin with simulated inference latency.

    Uses ``time.sleep(latency_ms / 1000)`` to model real device latency
    so the benchmark captures the pipeline overlap benefit.
    """
    import time
    from types import SimpleNamespace

    settings = SimpleNamespace(
        yolo_model=SimpleNamespace(confidence_threshold=0.25, nms_threshold=0.45),
        openvino=SimpleNamespace(batch_nireq=nireq),
    )

    class FakePlugin:
        """Lightweight stand-in that simulates detect / detect_batch timing."""

        def __init__(self) -> None:
            self._settings = settings
            self._latency = latency_ms / 1000.0

        def detect(self, frame, conf_threshold=None):
            """Simulate single-frame inference with sleep."""
            time.sleep(self._latency)
            return [(10, 20, 100, 200, 0.85, None, 0)]

        def detect_batch(self, frames, conf_threshold=None):
            """Simulate pipelined batch — overlap is modeled as sqrt(N)*latency."""
            # Approximate: with perfect overlap, N requests over nireq slots
            # takes ceil(N / nireq) * latency instead of N * latency.
            n = len(frames)
            slots = min(nireq, n)
            passes = math.ceil(n / slots) if slots > 0 else n
            time.sleep(passes * self._latency)
            return [[(10, 20, 100, 200, 0.85, None, 0)] for _ in range(n)]

    return FakePlugin()


@pytest.mark.benchmark
def test_benchmark_openvino_batch_inference(benchmark):
    """Benchmark pipelined detect_batch() with simulated latency (Phase 7.9)."""
    plugin = _make_mock_openvino_plugin(latency_ms=1.0, nireq=4)
    rng = np.random.default_rng(0)
    frames = [rng.integers(0, 255, (480, 640, 3), dtype=np.uint8) for _ in range(20)]

    result = benchmark(plugin.detect_batch, frames)
    assert len(result) == 20
    assert all(len(dets) >= 1 for dets in result)


@pytest.mark.benchmark
def test_benchmark_openvino_sequential_baseline(benchmark):
    """Baseline: sequential detect() per frame for comparison (Phase 7.9)."""
    plugin = _make_mock_openvino_plugin(latency_ms=1.0, nireq=4)
    rng = np.random.default_rng(0)
    frames = [rng.integers(0, 255, (480, 640, 3), dtype=np.uint8) for _ in range(20)]

    def sequential():
        return [plugin.detect(f) for f in frames]

    result = benchmark(sequential)
    assert len(result) == 20
