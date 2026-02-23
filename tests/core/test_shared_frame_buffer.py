"""Tests for SharedFrameBuffer — zero-copy IPC preview frames."""

from __future__ import annotations

import numpy as np
import pytest

from zebtrack.core.video.shared_frame_buffer import (
    DEFAULT_MAX_BYTES,
    SharedFrameBuffer,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_frame(h: int = 480, w: int = 640, c: int = 3) -> np.ndarray:
    """Return a random uint8 frame."""
    return np.random.randint(0, 255, (h, w, c), dtype=np.uint8)


# ---------------------------------------------------------------------------
# Basic round-trip
# ---------------------------------------------------------------------------


class TestSharedFrameBufferRoundTrip:
    """Verify write→read round-trip for different frame shapes."""

    def test_rgb_frame(self, tmp_path):
        frame = _make_frame(120, 160, 3)
        buf = SharedFrameBuffer(name="test_rgb", create=True)
        try:
            meta = buf.write(frame)
            assert "shm_seq" in meta
            assert meta["shm_shape"] == (120, 160, 3)
            assert meta["shm_dtype"] == "uint8"

            result = buf.read(meta["shm_seq"])
            assert result is not None
            np.testing.assert_array_equal(result, frame)
        finally:
            buf.close_and_unlink()

    def test_grayscale_frame(self):
        frame = np.random.randint(0, 255, (100, 100), dtype=np.uint8)
        buf = SharedFrameBuffer(name="test_gray", max_bytes=100 * 100, create=True)
        try:
            meta = buf.write(frame)
            assert meta["shm_shape"] == (100, 100)

            result = buf.read(meta["shm_seq"])
            assert result is not None
            np.testing.assert_array_equal(result, frame)
        finally:
            buf.close_and_unlink()

    def test_large_1080p_frame(self):
        frame = _make_frame(1080, 1920, 3)
        buf = SharedFrameBuffer(name="test_1080p", create=True)
        try:
            meta = buf.write(frame)
            result = buf.read(meta["shm_seq"])
            assert result is not None
            np.testing.assert_array_equal(result, frame)
        finally:
            buf.close_and_unlink()


# ---------------------------------------------------------------------------
# Sequence semantics
# ---------------------------------------------------------------------------


class TestSequenceNumber:
    """Verify sequence-based freshness checking."""

    def test_mismatched_seq_returns_none(self):
        buf = SharedFrameBuffer(name="test_seq_mismatch", create=True)
        try:
            frame = _make_frame(60, 80)
            meta = buf.write(frame)
            # Read with wrong sequence
            assert buf.read(meta["shm_seq"] + 1) is None
            assert buf.read(0) is None
        finally:
            buf.close_and_unlink()

    def test_sequence_increments(self):
        buf = SharedFrameBuffer(name="test_seq_inc", create=True)
        try:
            f1 = _make_frame(60, 80)
            f2 = _make_frame(60, 80)
            m1 = buf.write(f1)
            m2 = buf.write(f2)
            assert m2["shm_seq"] == m1["shm_seq"] + 1
            # Only latest is readable
            assert buf.read(m1["shm_seq"]) is None  # overwritten
            result = buf.read(m2["shm_seq"])
            assert result is not None
            np.testing.assert_array_equal(result, f2)
        finally:
            buf.close_and_unlink()


# ---------------------------------------------------------------------------
# Cross-process (attach)
# ---------------------------------------------------------------------------


class TestCrossProcessAttach:
    """Simulate producer/consumer by creating two handles to the same name."""

    def test_write_then_read_via_second_handle(self):
        owner = SharedFrameBuffer(name="test_cross", create=True)
        try:
            # Simulate worker attaching
            worker = SharedFrameBuffer(name="test_cross", create=False)
            try:
                frame = _make_frame(90, 120)
                meta = worker.write(frame)

                result = owner.read(meta["shm_seq"])
                assert result is not None
                np.testing.assert_array_equal(result, frame)
            finally:
                worker.close()
        finally:
            owner.close_and_unlink()


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Verify graceful error paths."""

    def test_frame_exceeds_max_bytes_raises(self):
        buf = SharedFrameBuffer(name="test_overflow", max_bytes=100, create=True)
        try:
            big_frame = _make_frame(100, 100)  # 30_000 bytes > 100
            with pytest.raises(ValueError, match="exceeds buffer capacity"):
                buf.write(big_frame)
        finally:
            buf.close_and_unlink()

    def test_read_before_any_write_returns_none(self):
        buf = SharedFrameBuffer(name="test_empty_read", create=True)
        try:
            assert buf.read(1) is None
        finally:
            buf.close_and_unlink()


# ---------------------------------------------------------------------------
# Properties and repr
# ---------------------------------------------------------------------------


class TestProperties:
    def test_name_property(self):
        buf = SharedFrameBuffer(name="test_props", create=True)
        try:
            assert buf.name == "test_props"
            assert buf.max_bytes == DEFAULT_MAX_BYTES
            assert "SharedFrameBuffer" in repr(buf)
        finally:
            buf.close_and_unlink()


# ---------------------------------------------------------------------------
# Integration: WorkerConfig shm_name field
# ---------------------------------------------------------------------------


class TestWorkerConfigShm:
    """Verify WorkerConfig accepts the shm_name field."""

    def test_shm_name_default_empty(self):
        from types import SimpleNamespace

        from zebtrack.core.video.processing_worker import WorkerConfig

        cfg = WorkerConfig(
            settings=SimpleNamespace(),
            output_base_dir="/tmp",
            tasks=[],
        )
        assert cfg.shm_name == ""

    def test_shm_name_set(self):
        from types import SimpleNamespace

        from zebtrack.core.video.processing_worker import WorkerConfig

        cfg = WorkerConfig(
            settings=SimpleNamespace(),
            output_base_dir="/tmp",
            tasks=[],
            shm_name="zebtrack_preview_99",
        )
        assert cfg.shm_name == "zebtrack_preview_99"
