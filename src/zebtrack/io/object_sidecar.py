"""The ``3c_Objetos_<base>.parquet`` sidecar: schema, metadata, reader, routing (ADR-010).

The trajectory (``3_CoordMovimento_``) holds subjects only and its schema is
immutable. Everything a start/stop condition needs about the OTHER classes lives
here instead: for every processed frame, one heartbeat row (``class_id == -1``,
``role == "frame"``, no bbox) plus one row per subject/context detection. The
heartbeat is what tells "nothing was detected" apart from "this frame was never
processed".

Columns, fixed order, additions only (a later version may append columns; the
reader accepts them)::

    frame:int64, timestamp:float64, t_event_s:float64, class_id:int16,
    class_name:dictionary<string>, role:dictionary<string>,
    x1, y1, x2, y2:float32, confidence:float32, track_id:int64, aquarium_id:int16

Coordinates are RAW VIDEO PIXELS, never calibrated, like the trajectory.

The recorder owns writing (``Recorder.write_object_data``); this module owns the
contract both sides share. pandas and pyarrow are imported lazily so importing
the module costs nothing at startup.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    import pandas as pd
    import pyarrow as pa

__all__ = [
    "CLOCK_CAPTURE",
    "CLOCK_PTS",
    "HEARTBEAT_CLASS_ID",
    "HEARTBEAT_ROLE",
    "MASK_SIDECAR_PREFIX",
    "OBJECTS_SCHEMA_VERSION",
    "OBJECT_COLUMNS",
    "OBJECT_SIDECAR_PREFIX",
    "TRAJECTORY_PREFIX",
    "ObjectSidecarMetadata",
    "build_object_table",
    "object_sidecar_name",
    "object_sidecar_schema",
    "partition_object_observations",
    "read_object_sidecar",
    "read_object_sidecar_metadata",
    "rebase_sidecar_name",
    "resolve_object_sidecar",
    "trajectory_sidecars",
]

log = structlog.get_logger()

#: File-name prefixes. ``3c_`` must never be a prefix of ``3_CoordMovimento``:
#: several readers glob the trajectory prefix and take the first match.
TRAJECTORY_PREFIX = "3_CoordMovimento_"
MASK_SIDECAR_PREFIX = "3b_Mascaras_"
OBJECT_SIDECAR_PREFIX = "3c_Objetos_"
FRAME_LEDGER_PREFIX = "6_FrameLedger_"
#: Same string as ``core.conditions.artifact.ARTIFACT_PREFIX`` (asserted by the
#: tests); duplicated so the I/O layer does not import the condition engine.
ANALYSIS_WINDOW_PREFIX = "7_AnalysisWindow_"

OBJECTS_SCHEMA_VERSION = "1"
HEARTBEAT_CLASS_ID = -1
HEARTBEAT_ROLE = "frame"

#: The event clock ``t_event_s`` is measured on (ADR-011 § Clocks).
CLOCK_PTS = "pts"
CLOCK_CAPTURE = "capture_perf"
_CLOCKS = frozenset({CLOCK_PTS, CLOCK_CAPTURE})

OBJECT_COLUMNS: tuple[str, ...] = (
    "frame",
    "timestamp",
    "t_event_s",
    "class_id",
    "class_name",
    "role",
    "x1",
    "y1",
    "x2",
    "y2",
    "confidence",
    "track_id",
    "aquarium_id",
)

_KEY_SCHEMA = "zebtrack.objects_schema"
_KEY_CLASS_NAMES = "class_names"
_KEY_CLASS_ROLES = "class_roles"
_KEY_WEIGHT_SHA = "weight_sha256"
_KEY_CLOCK = "clock"
_KEY_INTERVAL = "analysis_interval_frames"
_KEY_ROLES_SOURCE = "class_roles_source"

#: Sidecars that belong to one trajectory and must travel (and die) with it.
#: Suffixes after ``<prefix><base>``; the ledger also writes an anchor JSON.
_TRAJECTORY_SET: tuple[tuple[str, tuple[str, ...]], ...] = (
    (MASK_SIDECAR_PREFIX, (".parquet",)),
    (OBJECT_SIDECAR_PREFIX, (".parquet",)),
    (FRAME_LEDGER_PREFIX, (".csv", ".parquet", "_anchor.json")),
    (ANALYSIS_WINDOW_PREFIX, (".json",)),
)

#: Two context boxes of the same class from DIFFERENT aquarium crops with at
#: least this IoU are the same physical object seen twice.
_DUPLICATE_CONTEXT_IOU = 0.5


@dataclass(frozen=True)
class ObjectSidecarMetadata:
    """Parquet key-value metadata of the sidecar.

    Attributes:
        class_names: ``{class_id: model name}`` of the weight that produced it.
        class_roles: ``{normalised name: role token}`` actually applied.
        weight_sha256: sha256 of that weight (``""`` when unknown).
        clock: Clock of ``t_event_s`` — ``"pts"`` or ``"capture_perf"``.
        analysis_interval_frames: Detection cadence (``None`` when unknown).
        class_roles_source: Precedence level of the role map (``"project"``,
            ``"weight"``, ``"aliases"``, ``"legacy_positional"``; ``""`` when
            unknown). Not in ADR-010's list; an audit aid only.
    """

    class_names: Mapping[int, str] = field(default_factory=dict)
    class_roles: Mapping[str, str] = field(default_factory=dict)
    weight_sha256: str = ""
    clock: str = CLOCK_PTS
    analysis_interval_frames: int | None = None
    class_roles_source: str = ""

    def __post_init__(self) -> None:
        if self.clock not in _CLOCKS:
            raise ValueError(f"unknown clock {self.clock!r}; expected one of {sorted(_CLOCKS)}")

    @classmethod
    def from_role_map(
        cls,
        role_map: Any,
        *,
        clock: str,
        analysis_interval_frames: int | None,
        weight_sha256: str | None = None,
    ) -> ObjectSidecarMetadata:
        """Metadata from the RESOLVED ``ClassRoleMap`` the detector runs with.

        Args:
            role_map: The detector's ``class_role_map`` (``None`` when the
                detector has none, e.g. a test double).
            clock: Clock of ``t_event_s``.
            analysis_interval_frames: Detection cadence.
            weight_sha256: Overrides the map's sha (the worker's config carries
                the sha of the file it actually loaded).
        """
        names: dict[int, str] = {}
        roles: dict[str, str] = {}
        source = ""
        map_sha = ""
        if role_map is not None:
            names = {int(k): str(v) for k, v in dict(getattr(role_map, "names", {})).items()}
            roles_as_dict = getattr(role_map, "roles_as_dict", None)
            if callable(roles_as_dict):
                roles = {str(k): str(v) for k, v in roles_as_dict().items()}
            raw_source = getattr(role_map, "source", "")
            source = str(getattr(raw_source, "value", raw_source) or "")
            map_sha = str(getattr(role_map, "weight_sha256", "") or "")
        return cls(
            class_names=names,
            class_roles=roles,
            weight_sha256=weight_sha256 or map_sha,
            clock=clock,
            analysis_interval_frames=analysis_interval_frames,
            class_roles_source=source,
        )

    def to_parquet_metadata(self) -> dict[bytes, bytes]:
        """Encode as Parquet key-value metadata (JSON for the mappings)."""
        names = {str(k): v for k, v in sorted(self.class_names.items())}
        interval = ""
        if self.analysis_interval_frames is not None:
            interval = str(int(self.analysis_interval_frames))
        text = {
            _KEY_SCHEMA: OBJECTS_SCHEMA_VERSION,
            _KEY_CLASS_NAMES: json.dumps(names, ensure_ascii=False),
            _KEY_CLASS_ROLES: json.dumps(
                dict(self.class_roles), ensure_ascii=False, sort_keys=True
            ),
            _KEY_WEIGHT_SHA: self.weight_sha256,
            _KEY_CLOCK: self.clock,
            _KEY_INTERVAL: interval,
            _KEY_ROLES_SOURCE: self.class_roles_source,
        }
        return {key.encode("utf-8"): value.encode("utf-8") for key, value in text.items()}

    @classmethod
    def from_parquet_metadata(
        cls, raw: Mapping[bytes, bytes] | Mapping[str, str] | None
    ) -> ObjectSidecarMetadata:
        """Decode Parquet key-value metadata.

        Raises:
            ValueError: No ``zebtrack.objects_schema`` key, a version this code
                does not understand, or malformed values.
        """
        decoded: dict[str, str] = {}
        for key, value in (raw or {}).items():
            k = key.decode("utf-8") if isinstance(key, bytes) else str(key)
            v = value.decode("utf-8") if isinstance(value, bytes) else str(value)
            decoded[k] = v

        version = decoded.get(_KEY_SCHEMA)
        if version != OBJECTS_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported {_KEY_SCHEMA}={version!r}; expected {OBJECTS_SCHEMA_VERSION!r}"
            )
        try:
            names_raw = json.loads(decoded.get(_KEY_CLASS_NAMES) or "{}")
            roles_raw = json.loads(decoded.get(_KEY_CLASS_ROLES) or "{}")
            names = {int(k): str(v) for k, v in dict(names_raw).items()}
            roles = {str(k): str(v) for k, v in dict(roles_raw).items()}
            interval_text = decoded.get(_KEY_INTERVAL, "")
            interval = int(interval_text) if interval_text else None
        except (TypeError, ValueError) as exc:
            raise ValueError(f"malformed object sidecar metadata: {exc}") from exc
        return cls(
            class_names=names,
            class_roles=roles,
            weight_sha256=decoded.get(_KEY_WEIGHT_SHA, ""),
            clock=decoded.get(_KEY_CLOCK, ""),
            analysis_interval_frames=interval,
            class_roles_source=decoded.get(_KEY_ROLES_SOURCE, ""),
        )


# ---------------------------------------------------------------------------
# Schema and table
# ---------------------------------------------------------------------------


def object_sidecar_schema(metadata: ObjectSidecarMetadata) -> pa.Schema:
    """The Arrow schema of the sidecar, with its key-value metadata."""
    import pyarrow as pa

    label = pa.dictionary(pa.int32(), pa.string())
    fields = [
        pa.field("frame", pa.int64()),
        pa.field("timestamp", pa.float64()),
        pa.field("t_event_s", pa.float64()),
        pa.field("class_id", pa.int16()),
        pa.field("class_name", label),
        pa.field("role", label),
        pa.field("x1", pa.float32()),
        pa.field("y1", pa.float32()),
        pa.field("x2", pa.float32()),
        pa.field("y2", pa.float32()),
        pa.field("confidence", pa.float32()),
        pa.field("track_id", pa.int64()),
        pa.field("aquarium_id", pa.int16()),
    ]
    return pa.schema(fields, metadata=metadata.to_parquet_metadata())


def build_object_table(
    rows: Sequence[Mapping[str, Any]], metadata: ObjectSidecarMetadata
) -> pa.Table:
    """Columnar table of sidecar rows (each a dict keyed by :data:`OBJECT_COLUMNS`)."""
    import pyarrow as pa

    schema = object_sidecar_schema(metadata)
    arrays = []
    for schema_field in schema:
        values = [row.get(schema_field.name) for row in rows]
        if pa.types.is_dictionary(schema_field.type):
            arrays.append(pa.array(values, type=pa.string()).dictionary_encode())
        else:
            arrays.append(pa.array(values, type=schema_field.type))
    return pa.Table.from_arrays(arrays, schema=schema)


def object_sidecar_name(base_name: str) -> str:
    """File name of the sidecar for a recorder ``base_name``."""
    return f"{OBJECT_SIDECAR_PREFIX}{base_name}.parquet"


def _trajectory_base(trajectory_path: str | Path) -> str | None:
    name = Path(trajectory_path).name
    if not name.startswith(TRAJECTORY_PREFIX) or not name.endswith(".parquet"):
        return None
    return name[len(TRAJECTORY_PREFIX) : -len(".parquet")]


def resolve_object_sidecar(trajectory_path: str | Path | None) -> Path | None:
    """``3c_Objetos_*.parquet`` sibling of a trajectory, when it exists.

    Mirrors ``analysis_service.resolve_mask_sidecar``: the sidecar shares the
    trajectory's ``base_name`` (including any ``_aquarium_N`` suffix), so it is
    derived from the trajectory path instead of being threaded through callers.
    """
    if not trajectory_path:
        return None
    base = _trajectory_base(trajectory_path)
    if base is None:
        return None
    sidecar = Path(trajectory_path).with_name(object_sidecar_name(base))
    return sidecar if sidecar.exists() else None


def trajectory_sidecars(trajectory_path: str | Path) -> list[Path]:
    """Existing ``3b_``/``3c_``/``6_``/``7_`` files of the trajectory's base.

    Exact names only (no glob): ``CECT_4`` must never pick up ``CECT_40``.
    """
    base = _trajectory_base(trajectory_path)
    if base is None:
        return []
    folder = Path(trajectory_path).parent
    found: list[Path] = []
    for prefix, suffixes in _TRAJECTORY_SET:
        for suffix in suffixes:
            candidate = folder / f"{prefix}{base}{suffix}"
            if candidate.is_file():
                found.append(candidate)
    return found


def rebase_sidecar_name(sidecar: str | Path, trajectory_path: str | Path, new_base: str) -> str:
    """Name of ``sidecar`` once its trajectory is renamed to ``new_base``."""
    old_base = _trajectory_base(trajectory_path)
    name = Path(sidecar).name
    if old_base is None:
        raise ValueError(f"{trajectory_path} is not a trajectory file")
    for prefix, _suffixes in _TRAJECTORY_SET:
        head = f"{prefix}{old_base}"
        if name.startswith(head):
            return f"{prefix}{new_base}{name[len(head) :]}"
    raise ValueError(f"{name} is not a sidecar of {Path(trajectory_path).name}")


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


def _type_checks() -> dict[str, Any]:
    import pyarrow as pa

    def label(t: pa.DataType) -> bool:
        if pa.types.is_dictionary(t):
            return bool(pa.types.is_string(t.value_type) or pa.types.is_large_string(t.value_type))
        return bool(pa.types.is_string(t) or pa.types.is_large_string(t))

    integer = pa.types.is_integer
    floating = pa.types.is_floating
    return {
        "frame": integer,
        "timestamp": floating,
        "t_event_s": floating,
        "class_id": integer,
        "class_name": label,
        "role": label,
        "x1": floating,
        "y1": floating,
        "x2": floating,
        "y2": floating,
        "confidence": floating,
        "track_id": integer,
        "aquarium_id": integer,
    }


def _validate_schema(schema: pa.Schema, path: Path) -> ObjectSidecarMetadata | None:
    names = list(schema.names)
    if names[: len(OBJECT_COLUMNS)] != list(OBJECT_COLUMNS):
        log.warning(
            "object_sidecar.read.schema_mismatch",
            path=str(path),
            reason="columns",
            columns=names,
        )
        return None
    checks = _type_checks()
    for name in OBJECT_COLUMNS:
        if not checks[name](schema.field(name).type):
            log.warning(
                "object_sidecar.read.schema_mismatch",
                path=str(path),
                reason="type",
                column=name,
                type=str(schema.field(name).type),
            )
            return None
    try:
        return ObjectSidecarMetadata.from_parquet_metadata(schema.metadata)
    except ValueError as exc:
        log.warning(
            "object_sidecar.read.schema_mismatch",
            path=str(path),
            reason="metadata",
            error=str(exc),
        )
        return None


def read_object_sidecar_metadata(path: str | Path | None) -> ObjectSidecarMetadata | None:
    """Only the metadata (cheap: reads the footer). ``None`` on any problem."""
    if not path or not Path(path).is_file():
        return None
    import pyarrow as pa
    import pyarrow.parquet as pq

    try:
        schema = pq.read_schema(path)
    except (OSError, ValueError, pa.ArrowException) as exc:
        log.warning("object_sidecar.read.failed", path=str(path), error=str(exc))
        return None
    return _validate_schema(schema, Path(path))


def read_object_sidecar(path: str | Path | None) -> pd.DataFrame | None:
    """Read and validate a sidecar.

    Returns:
        The rows with ``class_name``/``role`` as plain strings (``None`` on the
        heartbeat), ``track_id`` as ``Int64`` and ``aquarium_id`` as ``Int16``
        (nullable), and the decoded :class:`ObjectSidecarMetadata` in
        ``df.attrs["objects_metadata"]``. ``None`` — with a warning, never an
        exception — when the file is missing, unreadable, or has an
        incompatible schema: a caller then behaves as if there were no sidecar.
    """
    if not path or not Path(path).is_file():
        return None
    import pandas as pd
    import pyarrow as pa
    import pyarrow.parquet as pq

    try:
        table = pq.read_table(path)
    except (OSError, ValueError, pa.ArrowException) as exc:
        log.warning("object_sidecar.read.failed", path=str(path), error=str(exc))
        return None

    metadata = _validate_schema(table.schema, Path(path))
    if metadata is None:
        return None

    for name in ("class_name", "role"):
        index = table.column_names.index(name)
        table = table.set_column(index, name, table.column(name).cast(pa.string()))
    df = table.to_pandas()
    df["track_id"] = (
        table.column("track_id")
        .cast(pa.int64())
        .to_pandas(types_mapper={pa.int64(): pd.Int64Dtype()}.get)
    )
    df["aquarium_id"] = (
        table.column("aquarium_id")
        .cast(pa.int16())
        .to_pandas(types_mapper={pa.int16(): pd.Int16Dtype()}.get)
    )
    df.attrs["objects_metadata"] = metadata
    return df


# ---------------------------------------------------------------------------
# Multi-aquarium routing
# ---------------------------------------------------------------------------


def _bbox_of(observation: Mapping[str, Any]) -> tuple[float, float, float, float] | None:
    bbox = observation.get("bbox")
    if bbox is None:
        return None
    try:
        values = tuple(float(v) for v in bbox)
    except (TypeError, ValueError):
        return None
    if len(values) != 4 or not all(math.isfinite(v) for v in values):
        return None
    return values[0], values[1], values[2], values[3]


def _iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    inter_w = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    inter_h = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = inter_w * inter_h
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def _containing_aquarium(
    point: tuple[float, float], polygons: Mapping[int, Any], ordered_ids: Iterable[int]
) -> int | None:
    import cv2
    import numpy as np

    for aquarium_id in ordered_ids:
        contour = np.asarray(polygons[aquarium_id], dtype=np.float32)
        if contour.size < 6:
            continue
        # Inclusive border, same convention as ``ZoneScaler.point_in_polygon``.
        if cv2.pointPolygonTest(contour.reshape(-1, 1, 2), point, False) >= 0:
            return aquarium_id
    return None


def _without_cross_crop_duplicates(
    observations: Sequence[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    """Drop boxes another aquarium's crop already reported (highest confidence wins).

    Each aquarium infers on its own crop, and with context classes the crop is
    WIDENED, so the experimenter's hand between two tanks (or a subject near
    the shared edge) is seen by both. Counted twice it would satisfy a
    ``min_count=2`` condition that is false.
    """
    kept: list[int] = []
    for index, item in enumerate(observations):
        box = _bbox_of(item)
        duplicate_of = None
        for position, other_index in enumerate(kept):
            other = observations[other_index]
            other_box = _bbox_of(other)
            if (
                other.get("role") == item.get("role")
                and other.get("class_id") == item.get("class_id")
                and other.get("aquarium_id") != item.get("aquarium_id")
                and box is not None
                and other_box is not None
                and _iou(box, other_box) >= _DUPLICATE_CONTEXT_IOU
            ):
                duplicate_of = position
                break
        if duplicate_of is None:
            kept.append(index)
            continue
        best = observations[kept[duplicate_of]]
        if float(item.get("confidence") or 0.0) > float(best.get("confidence") or 0.0):
            kept[duplicate_of] = index
    return [observations[i] for i in sorted(kept)]


def partition_object_observations(
    observations: Sequence[Mapping[str, Any]],
    aquarium_polygons: Mapping[int, Any],
) -> dict[int, list[dict[str, Any]]]:
    """Route one frame's observations to the aquarium recorders.

    Rules (ADR-010):

    - a subject row goes only to its own aquarium: the one containing its bbox
      centroid; outside every polygon, the aquarium whose crop saw it; with
      neither, it is dropped (it belongs to no aquarium);
    - a context row whose bbox centroid lies inside an aquarium polygon belongs
      to that aquarium;
    - a context row in no aquarium gets ``aquarium_id = None`` and is written to
      EVERY aquarium, because it applies to all of them;
    - the same object reported by two aquarium crops (same role and class, IoU
      >= 0.5) is kept once, with the higher confidence.

    Args:
        observations: Items of ``pop_class_observations()`` (full-frame bbox).
        aquarium_polygons: ``{aquarium_id: polygon}`` in the same (frame) pixels.

    Returns:
        ``{aquarium_id: [observation copies with the final aquarium_id]}`` with a
        key for every aquarium. Inputs are not mutated.
    """
    ordered_ids = sorted(aquarium_polygons)
    parts: dict[int, list[dict[str, Any]]] = {aquarium_id: [] for aquarium_id in ordered_ids}
    for item in _without_cross_crop_duplicates(observations):
        box = _bbox_of(item)
        if box is None:
            continue
        centroid = ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)
        owner = _containing_aquarium(centroid, aquarium_polygons, ordered_ids)
        if item.get("role") == "subject":
            if owner is None and item.get("aquarium_id") in parts:
                owner = item.get("aquarium_id")
            if owner is None:
                log.debug("object_sidecar.partition.subject_outside_aquariums", bbox=box)
                continue
            parts[owner].append({**item, "aquarium_id": owner})
            continue
        if owner is not None:
            parts[owner].append({**item, "aquarium_id": owner})
        else:
            for aquarium_id in ordered_ids:
                parts[aquarium_id].append({**item, "aquarium_id": None})
    return parts
