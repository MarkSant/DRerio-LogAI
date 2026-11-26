"""Write real ``3c_Objetos_`` sidecars next to a trajectory, for time-base tests.

Every analysis path dates a recording with
:func:`zebtrack.analysis.time_base.resolve_recording_time_base`, which reads the
``3c`` sibling of the trajectory from disk. The tests of each call site need a
real file (written by the production builder, read by the production reader),
not a mock of the reader, or they would prove nothing about the file lookup.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pyarrow.parquet as pq

from zebtrack.io.object_sidecar import (
    CLOCK_PTS,
    HEARTBEAT_CLASS_ID,
    HEARTBEAT_ROLE,
    TRAJECTORY_PREFIX,
    ObjectSidecarMetadata,
    build_object_table,
    object_sidecar_name,
)


def heartbeat_sidecar_path(trajectory_path: str | Path) -> Path:
    """Where the ``3c`` of ``3_CoordMovimento_<base>.parquet`` lives."""
    path = Path(trajectory_path)
    base = path.name[len(TRAJECTORY_PREFIX) : -len(".parquet")]
    return path.with_name(object_sidecar_name(base))


def write_heartbeat_sidecar(
    trajectory_path: str | Path,
    times: Sequence[float],
    *,
    frames: Sequence[int] | None = None,
    clock: str = CLOCK_PTS,
) -> Path:
    """A heartbeat-only ``3c`` (one row per processed frame) beside the trajectory."""
    frame_numbers = list(frames) if frames is not None else list(range(len(times)))
    rows = [
        {
            "frame": int(frame),
            "timestamp": float(t),
            "t_event_s": float(t),
            "class_id": HEARTBEAT_CLASS_ID,
            "class_name": None,
            "role": HEARTBEAT_ROLE,
            "x1": None,
            "y1": None,
            "x2": None,
            "y2": None,
            "confidence": None,
            "track_id": None,
            "aquarium_id": None,
        }
        for frame, t in zip(frame_numbers, times, strict=True)
    ]
    metadata = ObjectSidecarMetadata(
        class_names={0: "rat"},
        class_roles={"rat": "subject"},
        clock=clock,
        analysis_interval_frames=1,
    )
    target = heartbeat_sidecar_path(trajectory_path)
    pq.write_table(build_object_table(rows, metadata), target)
    return target
