"""SharedFrameBuffer: zero-copy preview frame transfer via shared memory.

The producer (worker process) writes preview frames into a fixed-size shared
memory block.  The consumer (monitor thread in main process) reads the frame
after receiving a lightweight queue message with shape/dtype metadata.

Layout (contiguous byte offset):

    [0:4]   — sequence number  (uint32, little-endian)
    [4:8]   — height           (uint32)
    [8:12]  — width            (uint32)
    [12:16] — channels         (uint32)
    [16:N]  — raw pixel data   (N = h * w * c * dtype_itemsize)

Typical use
-----------
**Producer** (worker process)::

    buf = SharedFrameBuffer(name="zebtrack_preview_12345", create=False)
    meta = buf.write(preview_frame)          # returns {"shm_seq": seq}
    result_queue.put({**meta, "type": "frame", "detections": ...})

**Consumer** (monitor thread)::

    buf = SharedFrameBuffer(name="zebtrack_preview_12345",
                            max_bytes=MAX, create=True)
    msg = result_queue.get()
    frame = buf.read(msg["shm_seq"])         # np.ndarray | None
    if frame is not None:
        callbacks.on_frame_processed(frame, ...)

When shared memory is unavailable or fails, the caller must gracefully
fall back to regular pickle-based queue transfer.
"""

from __future__ import annotations

import struct
from multiprocessing.shared_memory import SharedMemory
from typing import Any

import numpy as np
import structlog

log = structlog.get_logger()

# 4 uint32 values: sequence, height, width, channels
HEADER_FMT = "<4I"
HEADER_SIZE = struct.calcsize(HEADER_FMT)  # 16 bytes

# Default max buffer: 1920 × 1080 × 3 (RGB) ≈ 6.2 MB
DEFAULT_MAX_BYTES = 1920 * 1080 * 3


class SharedFrameBuffer:
    """Single-slot shared memory buffer for numpy preview frames.

    Parameters
    ----------
    name:
        Unique name for the shared memory block.  Both producer and consumer
        must use the same name.
    max_bytes:
        Maximum payload size in bytes (default 6.2 MB for 1080p RGB).
    create:
        ``True`` to create the shared memory block (caller owns lifecycle).
        ``False`` to attach to an existing block.
    """

    def __init__(
        self,
        name: str,
        max_bytes: int = DEFAULT_MAX_BYTES,
        create: bool = True,
    ) -> None:
        self._name = name
        self._max_bytes = max_bytes
        self._seq: int = 0
        total_size = HEADER_SIZE + max_bytes

        try:
            self._shm = SharedMemory(name=name, create=create, size=total_size)
        except Exception:
            log.warning(
                "shared_frame_buffer.init_failed",
                name=name,
                create=create,
                exc_info=True,
            )
            raise

        log.debug(
            "shared_frame_buffer.init",
            name=self._shm.name,
            size=self._shm.size,
            create=create,
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        """Return the underlying shared memory name."""
        return self._shm.name

    @property
    def max_bytes(self) -> int:
        return self._max_bytes

    # ------------------------------------------------------------------
    # Producer API
    # ------------------------------------------------------------------

    def write(self, frame: np.ndarray) -> dict[str, Any]:
        """Write *frame* into the shared buffer and return metadata.

        The returned dict should be merged into the queue message so the
        consumer can call :meth:`read` with the matching sequence number.

        Returns
        -------
        dict
            ``{"shm_seq": <int>, "shm_shape": <tuple>, "shm_dtype": <str>}``

        Raises
        ------
        ValueError
            If the frame exceeds *max_bytes*.
        """
        data = np.ascontiguousarray(frame)
        nbytes = data.nbytes

        if nbytes > self._max_bytes:
            raise ValueError(f"Frame size {nbytes} exceeds buffer capacity {self._max_bytes}")

        h, w = data.shape[:2]
        c = data.shape[2] if data.ndim == 3 else 1

        self._seq += 1
        seq = self._seq

        # Write header
        header = struct.pack(HEADER_FMT, seq, h, w, c)
        self._shm.buf[:HEADER_SIZE] = header

        # Write pixel data
        self._shm.buf[HEADER_SIZE : HEADER_SIZE + nbytes] = data.tobytes()

        return {
            "shm_seq": seq,
            "shm_shape": (h, w, c) if c > 1 else (h, w),
            "shm_dtype": str(data.dtype),
        }

    # ------------------------------------------------------------------
    # Consumer API
    # ------------------------------------------------------------------

    def read(self, expected_seq: int) -> np.ndarray | None:
        """Read the current frame if it matches *expected_seq*.

        Returns ``None`` when the sequence number does not match (the frame
        was already overwritten) or when the header is invalid.
        """
        try:
            seq, h, w, c = struct.unpack(HEADER_FMT, bytes(self._shm.buf[:HEADER_SIZE]))
        except struct.error:
            return None

        if seq != expected_seq:
            return None

        if h == 0 or w == 0:
            return None

        shape: tuple[int, ...] = (h, w, c) if c > 1 else (h, w)
        nbytes = h * w * c  # uint8 assumed
        if HEADER_SIZE + nbytes > self._shm.size:
            return None

        raw = bytes(self._shm.buf[HEADER_SIZE : HEADER_SIZE + nbytes])
        return np.frombuffer(raw, dtype=np.uint8).reshape(shape).copy()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close handle to shared memory (does NOT unlink)."""
        try:
            self._shm.close()
        except Exception:  # noqa: S110 — cleanup must not propagate
            pass

    def unlink(self) -> None:
        """Release the underlying shared memory resource.

        Only the *owner* (``create=True``) should call this.
        """
        try:
            self._shm.unlink()
        except Exception:
            log.debug("shared_frame_buffer.unlink_failed", name=self._name, exc_info=True)

    def close_and_unlink(self) -> None:
        """Convenience: close then unlink."""
        self.close()
        self.unlink()

    def __repr__(self) -> str:
        return (
            f"SharedFrameBuffer(name={self._name!r}, max_bytes={self._max_bytes}, seq={self._seq})"
        )
