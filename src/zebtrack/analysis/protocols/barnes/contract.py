"""The Barnes-maze contract every Barnes front codes against (ADR-014, #633).

Pure data and pure functions: names, tokens, parameters, the layout schema and the
metrics schema. No geometry fitting, no metric computation and no UI live here —
those belong to the fronts listed in ``docs/tasks/v8.1/barnes/PLAN.md``. Anything
two fronts must agree on is defined HERE, once.

Conventions that hold everywhere below:

* **Offsets are relative to the escape hole (the target).** ``0`` is the target;
  ``+k`` is ``k`` holes CLOCKWISE as seen on screen (image coordinates, y pointing
  down, so the angle ``atan2(y - cy, x - cx)`` grows clockwise); ``-k`` is ``k``
  holes counter-clockwise. With an even ``n_holes`` the opposite hole is
  ``+n_holes // 2`` (never negative). Relative offsets keep columns comparable
  across days when the target moves (working-memory protocol).
* **Distance** of a hole is ``abs(offset)``: ``0`` .. ``n_holes // 2``.
* **ROI names are the contract**, not ``ZoneData.metadata``: the metadata is lost by
  the ``2_AreasOfInterest`` parquet, ROI templates and ``apply_template``, while the
  names survive everywhere. The layout can always be rebuilt from names + polygons.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final, Literal

import structlog
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from zebtrack.core.conditions.presets import BARNES_BURROW_ROI
from zebtrack.i18n import _

__all__ = [
    "ASSISTANT_ID",
    "EXCEL_VISITS_SHEET",
    "EXCEL_VISIT_COLUMNS",
    "HOLE_ROI_PREFIX",
    "LAYOUT_METADATA_KEY",
    "LAYOUT_SCHEMA_VERSION",
    "METRICS_KEYS",
    "METRICS_VERSION",
    "OPPOSITE_HOLE_ROI",
    "QUADRANT_ROI",
    "STOP_REASON_BURROW_ENTRY",
    "TARGET_ROI",
    "VISIT_FIELDS",
    "BarnesEllipse",
    "BarnesHole",
    "BarnesLayout",
    "BarnesParams",
    "BarnesRoiKind",
    "BarnesRoiName",
    "BarnesVideoInputs",
    "EntrySource",
    "SearchStrategy",
    "StartSource",
    "StrategySource",
    "TrialType",
    "barnes_tidy_columns",
    "circular_offset",
    "expected_roi_names",
    "hole_roi_name",
    "max_offset",
    "parse_barnes_params",
    "parse_barnes_roi_name",
    "parse_barnes_video_inputs",
    "probe_score",
    "tidy_column_source",
]

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Names and tokens (persistence contracts: never translated)
# ---------------------------------------------------------------------------

#: The escape hole. Same token the analysis-window preset matches (``RoiEdge`` /
#: ``BurrowEntry``), so a layout drawn by the assistant fires the preset.
TARGET_ROI: Final = BARNES_BURROW_ROI
#: The target quadrant: a sector from the table centre covering the target and
#: ``quadrant_half_holes`` holes on each side.
QUADRANT_ROI: Final = "quadrante_alvo"
#: The hole opposite the target (only when ``n_holes`` is even).
OPPOSITE_HOLE_ROI: Final = "buraco_oposto"
#: Prefix of every decoy hole except the opposite one: ``buraco_+01``, ``buraco_-09``.
HOLE_ROI_PREFIX: Final = "buraco_"

#: ``ZoneData.metadata`` key of the cached :class:`BarnesLayout`.
LAYOUT_METADATA_KEY: Final = "barnes_layout"
LAYOUT_SCHEMA_VERSION: Final = 1

#: ``report["protocol_metrics"]["version"]`` of the Barnes metrics.
METRICS_VERSION: Final = 1

#: STOP reason of the analysis window when the rat entered the escape hole
#: (``BurrowEntry`` trigger, preset v2). Added to ``WindowReason`` by ``barnes-entry``.
STOP_REASON_BURROW_ENTRY: Final = "burrow_entry"

#: ``ProtocolSpec.zone_assistant`` of the Barnes layout assistant.
ASSISTANT_ID: Final = "barnes_layout"

#: Sheet of the individual ``.xlsx`` with one row per hole visit.
EXCEL_VISITS_SHEET: Final = "barnes_visits"

_HOLE_NAME_RE = re.compile(r"^buraco_([+-])(\d{2})$")


class TrialType(StrEnum):
    """Kind of trial a video records. Persisted per video."""

    TRAINING = "training"
    PROBE = "probe"


class SearchStrategy(StrEnum):
    """Search strategy of one trial (lab protocol: direct / serial / random)."""

    DIRECT = "direct"
    SERIAL = "serial"
    RANDOM = "random"


class StrategySource(StrEnum):
    """Where ``strategy`` came from."""

    AUTO = "auto"
    MANUAL = "manual"


class StartSource(StrEnum):
    """Where ``t_start_s`` (the trial's t0) came from."""

    #: START of the analysis window.
    WINDOW = "window"
    #: No window START: the first timestamp of the trajectory (warned).
    RECORDING = "recording"


class EntrySource(StrEnum):
    """Where ``entry_latency_s`` came from."""

    #: The window's STOP with reason ``burrow_entry``.
    WINDOW = "window"
    #: The trial ended without an entry (ceiling or end of recording): censored.
    CENSORED = "censored"
    #: No window able to detect an entry (no window, or a v1 preset): ``None``.
    UNAVAILABLE = "unavailable"
    #: Probe trial: there is no escape box, entry is not measured.
    NOT_APPLICABLE = "not_applicable"


# ---------------------------------------------------------------------------
# Offsets and ROI names
# ---------------------------------------------------------------------------


def max_offset(n_holes: int) -> int:
    """Largest distance a hole can have from the target: ``n_holes // 2``."""
    if n_holes < 3:
        raise ValueError(f"n_holes must be at least 3, got {n_holes!r}")
    return n_holes // 2


def circular_offset(abs_index: int, target_abs_index: int, n_holes: int) -> int:
    """Signed offset of ``abs_index`` from the target, in ``(-n/2, n/2]``.

    ``abs_index`` counts clockwise on screen. With an even ``n_holes`` the opposite
    hole is ``+n_holes // 2``.
    """
    half = max_offset(n_holes)
    delta = (abs_index - target_abs_index) % n_holes
    if delta > half:
        delta -= n_holes
    return delta


def hole_roi_name(offset: int, n_holes: int) -> str:
    """ROI name of the hole at ``offset`` from the target.

    ``0`` → ``toca``; the opposite hole (even ``n_holes``) → ``buraco_oposto``;
    others → ``buraco_+01`` .. ``buraco_-09`` (sign always written, two digits).

    Raises:
        ValueError: ``offset`` is outside ``[-n_holes // 2, n_holes // 2]``, or is
            ``-n_holes // 2`` for an even ``n_holes`` (the opposite is ``+``).
    """
    half = max_offset(n_holes)
    if not -half <= offset <= half:
        raise ValueError(f"offset {offset!r} outside ±{half} for {n_holes} holes")
    if offset == 0:
        return TARGET_ROI
    if n_holes % 2 == 0 and abs(offset) == half:
        if offset < 0:
            raise ValueError(f"the opposite hole is +{half}, not {offset}")
        return OPPOSITE_HOLE_ROI
    return f"{HOLE_ROI_PREFIX}{offset:+03d}"


def expected_roi_names(n_holes: int) -> tuple[str, ...]:
    """Every Barnes ROI name, in the stored order the assistant writes.

    Order: ``quadrante_alvo``; ``toca``; ``buraco_+01`` .. ``buraco_+k``;
    ``buraco_-01`` .. ``buraco_-k``; ``buraco_oposto`` (even ``n_holes``). The
    quadrant comes first so that, where it overlaps a hole, the hole wins
    ``ROIAnalyzer``'s single ``stable_roi`` column (the last ROI in order wins).
    """
    half = max_offset(n_holes)
    side = half - 1 if n_holes % 2 == 0 else half
    names = [QUADRANT_ROI, TARGET_ROI]
    names.extend(hole_roi_name(k, n_holes) for k in range(1, side + 1))
    names.extend(hole_roi_name(-k, n_holes) for k in range(1, side + 1))
    if n_holes % 2 == 0:
        names.append(OPPOSITE_HOLE_ROI)
    return tuple(names)


class BarnesRoiKind(StrEnum):
    """What a Barnes ROI name denotes."""

    QUADRANT = "quadrant"
    HOLE = "hole"


@dataclass(frozen=True, slots=True)
class BarnesRoiName:
    """A parsed Barnes ROI name. ``offset`` is ``None`` for the quadrant."""

    kind: BarnesRoiKind
    offset: int | None


def parse_barnes_roi_name(name: str, n_holes: int) -> BarnesRoiName | None:
    """Parse a ROI name against the contract; ``None`` when it is not a Barnes ROI.

    Exact and case-sensitive: the names are generated, never typed. A hole name
    whose offset does not fit ``n_holes`` is not a Barnes ROI of this layout.
    """
    if name == QUADRANT_ROI:
        return BarnesRoiName(BarnesRoiKind.QUADRANT, None)
    if name == TARGET_ROI:
        return BarnesRoiName(BarnesRoiKind.HOLE, 0)
    half = max_offset(n_holes)
    if name == OPPOSITE_HOLE_ROI:
        if n_holes % 2 == 0:
            return BarnesRoiName(BarnesRoiKind.HOLE, half)
        return None
    match = _HOLE_NAME_RE.match(name)
    if match is None:
        return None
    offset = int(match.group(2)) * (1 if match.group(1) == "+" else -1)
    if offset == 0 or abs(offset) > half or (n_holes % 2 == 0 and abs(offset) == half):
        return None
    return BarnesRoiName(BarnesRoiKind.HOLE, offset)


def probe_score(offset: int, cap: int) -> int:
    """Probe error score of the first hole visited: ``min(abs(offset) + 1, cap)``.

    Target = 1, +1 per hole away. With the lab's 20 holes the opposite hole is 11
    holes from "1", so the protocol's "opposite = 10" only holds with ``cap = 10``
    (the default; still to be confirmed by the lab).
    """
    if cap < 1:
        raise ValueError(f"cap must be at least 1, got {cap!r}")
    return min(abs(offset) + 1, cap)


# ---------------------------------------------------------------------------
# Parameters (behavioral_config["protocol_params"]["barnes"])
# ---------------------------------------------------------------------------


class BarnesParams(BaseModel):
    """Every Barnes threshold. Defaults are the lab protocol / plan values.

    Read from ``ExperimentProfile.protocol_params`` with :func:`parse_barnes_params`;
    never construct it from raw project data with ``BarnesParams(**raw)``.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    # -- table and layout --------------------------------------------------
    #: Holes around the rim (the lab's table: 20).
    n_holes: int = Field(default=20, ge=3, le=99)
    #: Table diameter, for px/cm (the lab's table: 184 cm).
    table_diameter_cm: float = Field(default=184.0, gt=0.0)
    #: Holes on EACH side of the target inside ``quadrante_alvo`` (2 → 5 holes).
    quadrant_half_holes: int = Field(default=2, ge=0)
    #: Hole ROI radius / detected hole radius. The assistant caps the resulting
    #: radius below half the hole spacing so hole ROIs never overlap.
    hole_roi_dilation: float = Field(default=1.25, ge=1.0, le=3.0)
    #: Radius of the "centre" disk (search strategy) / radius of the hole ring.
    center_radius_ratio: float = Field(default=0.5, gt=0.0, lt=1.0)

    # -- trial ---------------------------------------------------------------
    #: Protocol ceiling: an entry that never happens is censored at this latency.
    max_trial_s: float = Field(default=240.0, gt=0.0)
    #: Trial type of a video that does not declare its own.
    default_trial_type: TrialType = TrialType.TRAINING
    #: Probe score ceiling (see :func:`probe_score`).
    probe_score_cap: int = Field(default=10, ge=1)

    # -- hole visits (nose pokes) ------------------------------------------
    #: Fraction of the hole DISK covered by the subject bbox for a visit.
    visit_min_cover: float = Field(default=0.3, gt=0.0, le=1.0)
    #: Consecutive covered frames that open a visit (back-dated).
    visit_enter_frames: int = Field(default=2, ge=1)
    #: Consecutive uncovered frames that close a visit (back-dated).
    visit_exit_frames: int = Field(default=3, ge=1)
    #: Optional slowdown filter: a visit also needs the subject below this speed
    #: (cm/s) on at least one covered frame. ``None`` disables it.
    visit_max_speed_cm_s: float | None = Field(default=None, gt=0.0)

    # -- burrow entry (four paws in): BurrowEntry trigger of preset v2 -------
    #: Fraction of the subject BBOX inside the target ROI.
    entry_min_cover: float = Field(default=0.5, gt=0.0, le=1.0)
    #: Visible size: subject bbox area / running median of its area since START.
    entry_max_visible_fraction: float = Field(default=0.35, gt=0.0, lt=1.0)
    #: How long "over the target and small" must hold.
    entry_hold_s: float = Field(default=0.5, gt=0.0)
    #: How long the subject must be absent, last seen in the target, to count.
    entry_absent_s: float = Field(default=3.0, gt=0.0)
    #: Detected frames since START before the running median is trusted.
    entry_min_reference_frames: int = Field(default=10, ge=1)

    # -- search strategy -----------------------------------------------------
    #: Direct: at most this many errors before the target, no centre crossing.
    strategy_direct_max_errors: int = Field(default=3, ge=0)
    #: Serial: at least this fraction of hole-to-hole transitions are adjacent.
    strategy_serial_min_adjacent_fraction: float = Field(default=2.0 / 3.0, gt=0.0, le=1.0)
    #: Serial: at most this many centre crossings.
    strategy_serial_max_center_crossings: int = Field(default=1, ge=0)
    #: A transition is "adjacent" when ``abs(Δoffset) <= this``.
    strategy_adjacent_max_step: int = Field(default=2, ge=1)

    @model_validator(mode="after")
    def _quadrant_fits(self) -> BarnesParams:
        if 2 * self.quadrant_half_holes + 1 > self.n_holes:
            raise ValueError(
                f"quadrant_half_holes={self.quadrant_half_holes} does not fit {self.n_holes} holes"
            )
        return self


def _invalid_fields(error: ValidationError, raw: Mapping[str, Any]) -> set[str]:
    names: set[str] = set()
    for item in error.errors():
        loc = item.get("loc") or ()
        if loc and isinstance(loc[0], str) and loc[0] in raw:
            names.add(loc[0])
    return names


def parse_barnes_params(raw: Mapping[str, Any] | None) -> tuple[BarnesParams, tuple[str, ...]]:
    """Validate the Barnes params; a bad field falls back to its default, with a warning.

    Never raises. A cross-field failure that dropping the offending fields cannot
    fix (``quadrant_half_holes`` against ``n_holes``) drops both and keeps the
    defaults. Unknown keys are ignored (a newer version's parameter).

    Returns:
        ``(params, warnings)`` — warnings are translated and user-facing.
    """
    data: dict[str, Any] = dict(raw) if isinstance(raw, Mapping) else {}
    warnings: list[str] = []
    for _attempt in range(len(BarnesParams.model_fields) + 1):
        try:
            return BarnesParams.model_validate(data), tuple(warnings)
        except ValidationError as exc:
            bad = _invalid_fields(exc, data)
            if not bad:
                # A model-level rule: drop the fields it is about.
                bad = {"quadrant_half_holes", "n_holes"} & set(data)
            if not bad:
                break
            for name in sorted(bad):
                logger.warning("barnes.params.invalid", field=name, value=repr(data[name]))
                warnings.append(
                    _("Invalid Barnes parameter {name}={value}; its default is used.").format(
                        name=name, value=repr(data[name])
                    )
                )
                del data[name]
    return BarnesParams(), tuple(warnings)


# ---------------------------------------------------------------------------
# Per-video inputs (video_entry["protocol_inputs"]["barnes"])
# ---------------------------------------------------------------------------


class BarnesVideoInputs(BaseModel):
    """What the researcher declared for ONE video.

    Persisted as ``video_entry["protocol_inputs"]["barnes"] = {"trial_type": ...,
    "strategy_override": ...}`` through ``set_protocol_input``. ``None`` means
    "not declared": the trial type falls back to ``BarnesParams.default_trial_type``
    and the strategy is the automatic one.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    trial_type: TrialType | None = None
    strategy_override: SearchStrategy | None = None


def parse_barnes_video_inputs(
    raw: Mapping[str, Any] | None,
) -> tuple[BarnesVideoInputs, tuple[str, ...]]:
    """Validate one video's inputs; a bad field is dropped with a warning. Never raises."""
    data: dict[str, Any] = dict(raw) if isinstance(raw, Mapping) else {}
    warnings: list[str] = []
    for name in ("trial_type", "strategy_override"):
        if name not in data or data[name] is None:
            continue
        try:
            BarnesVideoInputs.model_validate({name: data[name]})
        except ValidationError:
            logger.warning("barnes.video_inputs.invalid", field=name, value=repr(data[name]))
            warnings.append(
                _("Invalid Barnes value {name}={value} for this video; it is ignored.").format(
                    name=name, value=repr(data[name])
                )
            )
            del data[name]
    return BarnesVideoInputs.model_validate(data), tuple(warnings)


# ---------------------------------------------------------------------------
# Layout (ZoneData.metadata["barnes_layout"]) — a cache; names are the contract
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BarnesEllipse:
    """An ellipse in the pixel space of the frame it was drawn on.

    ``angle_deg`` follows OpenCV's ``cv2.fitEllipse`` / ``cv2.ellipse`` convention
    (rotation of the first semi-axis, degrees, image coordinates).
    """

    center_px: tuple[float, float]
    semi_axes_px: tuple[float, float]
    angle_deg: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "center_px": [self.center_px[0], self.center_px[1]],
            "semi_axes_px": [self.semi_axes_px[0], self.semi_axes_px[1]],
            "angle_deg": self.angle_deg,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> BarnesEllipse:
        cx, cy = (float(v) for v in raw["center_px"])
        a, b = (float(v) for v in raw["semi_axes_px"])
        angle = float(raw["angle_deg"])
        if not all(math.isfinite(v) for v in (cx, cy, a, b, angle)) or a <= 0 or b <= 0:
            raise ValueError("ellipse values must be finite with positive semi-axes")
        return cls(center_px=(cx, cy), semi_axes_px=(a, b), angle_deg=angle)


@dataclass(frozen=True, slots=True)
class BarnesHole:
    """One hole of the layout.

    Attributes:
        offset: Signed offset from the target (module conventions).
        abs_index: Position around the ring, ``0..n_holes-1``, clockwise on screen.
            Index 0 is the assistant's choice (any fixed origin); only differences
            matter.
        center_px: Hole centre.
        radius_px: Hole radius BEFORE ``hole_roi_dilation`` (detected, or predicted).
        snapped: ``True`` when ``center_px`` came from a detected dark blob.
        residual_px: Distance prediction → snapped centre (``None`` if not snapped).
    """

    offset: int
    abs_index: int
    center_px: tuple[float, float]
    radius_px: float
    snapped: bool = False
    residual_px: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "offset": self.offset,
            "abs_index": self.abs_index,
            "center_px": [self.center_px[0], self.center_px[1]],
            "radius_px": self.radius_px,
            "snapped": self.snapped,
            "residual_px": self.residual_px,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> BarnesHole:
        cx, cy = (float(v) for v in raw["center_px"])
        radius = float(raw["radius_px"])
        residual = raw.get("residual_px")
        if not all(math.isfinite(v) for v in (cx, cy, radius)) or radius <= 0:
            raise ValueError("hole values must be finite with a positive radius")
        return cls(
            offset=int(raw["offset"]),
            abs_index=int(raw["abs_index"]),
            center_px=(cx, cy),
            radius_px=radius,
            snapped=bool(raw.get("snapped", False)),
            residual_px=None if residual is None else float(residual),
        )


LayoutSource = Literal["auto", "click", "snapped", "reconstructed"]
_LAYOUT_SOURCES: tuple[str, ...] = ("auto", "click", "snapped", "reconstructed")


@dataclass(frozen=True, slots=True)
class BarnesLayout:
    """A Barnes table as drawn on one video.

    Attributes:
        n_holes: Holes around the rim.
        target_abs_index: ``abs_index`` of the escape hole.
        table: Outline of the table (the arena polygon is this ellipse, densified).
        ring: Ellipse through the hole centres.
        holes: Every hole, sorted by ``abs_index``; offsets match ``target_abs_index``.
        source: ``auto`` (no click), ``click`` (target clicked, no snapping),
            ``snapped`` (holes snapped to dark blobs), ``reconstructed`` (rebuilt
            from ROI names and polygons by the metrics front).
        schema: Layout schema version (:data:`LAYOUT_SCHEMA_VERSION`).
    """

    n_holes: int
    target_abs_index: int
    table: BarnesEllipse
    ring: BarnesEllipse
    holes: tuple[BarnesHole, ...]
    source: LayoutSource = "click"
    schema: int = LAYOUT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema != LAYOUT_SCHEMA_VERSION:
            raise ValueError(f"unsupported layout schema {self.schema!r}")
        if self.source not in _LAYOUT_SOURCES:
            raise ValueError(f"unknown layout source {self.source!r}")
        if len(self.holes) != self.n_holes:
            raise ValueError(f"{len(self.holes)} holes for n_holes={self.n_holes}")
        if not 0 <= self.target_abs_index < self.n_holes:
            raise ValueError(f"target_abs_index {self.target_abs_index!r} out of range")
        indices = [hole.abs_index for hole in self.holes]
        if indices != list(range(self.n_holes)):
            raise ValueError("holes must be sorted by abs_index 0..n_holes-1")
        for hole in self.holes:
            expected = circular_offset(hole.abs_index, self.target_abs_index, self.n_holes)
            if hole.offset != expected:
                raise ValueError(
                    f"hole {hole.abs_index} has offset {hole.offset}, expected {expected}"
                )

    @property
    def target(self) -> BarnesHole:
        return self.holes[self.target_abs_index]

    def to_metadata(self) -> dict[str, Any]:
        """JSON form stored under ``ZoneData.metadata["barnes_layout"]``."""
        return {
            "schema": self.schema,
            "n_holes": self.n_holes,
            "target_abs_index": self.target_abs_index,
            "source": self.source,
            "table": self.table.to_dict(),
            "ring": self.ring.to_dict(),
            "holes": [hole.to_dict() for hole in self.holes],
        }

    @classmethod
    def from_metadata(cls, raw: Any) -> BarnesLayout | None:
        """Rebuild from the metadata form; ``None`` (logged) when absent or invalid.

        Never raises: a stale or hand-edited cache is ignored and the caller
        rebuilds the layout from the ROI names.
        """
        if raw is None:
            return None
        if not isinstance(raw, Mapping):
            logger.warning("barnes.layout.metadata_invalid", value_type=type(raw).__name__)
            return None
        try:
            return cls(
                n_holes=int(raw["n_holes"]),
                target_abs_index=int(raw["target_abs_index"]),
                table=BarnesEllipse.from_dict(raw["table"]),
                ring=BarnesEllipse.from_dict(raw["ring"]),
                holes=tuple(BarnesHole.from_dict(item) for item in raw["holes"]),
                source=raw.get("source", "click"),
                schema=int(raw.get("schema", LAYOUT_SCHEMA_VERSION)),
            )
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("barnes.layout.metadata_invalid", error=str(exc))
            return None


# ---------------------------------------------------------------------------
# Metrics schema (report["protocol_metrics"] when protocol == "barnes")
# ---------------------------------------------------------------------------

#: Keys of ``report["protocol_metrics"]`` with ``status == "ok"``, in order.
#: Units: seconds relative to ``t_start_s`` unless stated; distances in cm.
METRICS_KEYS: Final[tuple[str, ...]] = (
    "status",  # "ok"
    "protocol",  # "barnes"
    "version",  # METRICS_VERSION
    "reason",  # None when ok
    "trial_type",  # TrialType token
    "n_holes",  # int
    "t_start_s",  # float, absolute on the trajectory's timestamp clock
    "start_source",  # StartSource token
    "encounter_latency_s",  # float; = max_trial_s when censored
    "encounter_censored",  # bool
    "entry_latency_s",  # float | None; = max_trial_s when censored; None for probe/unavailable
    "entry_censored",  # bool | None (None for probe/unavailable)
    "entry_source",  # EntrySource token
    "primary_errors",  # int: decoy-hole visits before the first target visit
    "total_errors",  # int: decoy-hole visits until entry (training) or trial end (probe)
    "perseverative_errors",  # int: decoy visits to a hole already visited (subset of total)
    "primary_path_length_cm",  # float | None: path START -> first target visit
    "entry_path_length_cm",  # float | None: path START -> entry
    "target_quadrant_time_s",  # float: time in quadrante_alvo within the trial
    "target_quadrant_time_pct",  # float 0-100 of the trial length
    "visits_by_distance",  # dict[int, int]: distance 0..n/2 -> visits (every distance present)
    "visit_sequence",  # list[dict] with VISIT_FIELDS
    "strategy",  # SearchStrategy token | None (effective: manual if overridden)
    "strategy_source",  # StrategySource token | None
    "strategy_auto",  # SearchStrategy token | None (always the automatic result)
    "strategy_features",  # dict: errors_before_target, center_crossings,
    #                       adjacent_transition_fraction (float|None), n_transitions
    "probe_first_hole_offset",  # int | None (probe only)
    "probe_first_hole_score",  # int | None (probe only; probe_score())
    "probe_first_error_latency_s",  # float | None (probe; None if the 1st visit is the target)
    "probe_attempts_to_target",  # int | None (probe; visits up to and incl. the 1st target visit)
)

#: Fields of each ``visit_sequence`` entry (also the ``barnes_visits`` sheet).
VISIT_FIELDS: Final[tuple[str, ...]] = (
    "order",  # int, 1-based
    "roi",  # ROI name (toca / buraco_+01 / ...)
    "offset",  # int
    "distance",  # int abs(offset)
    "t_enter_s",  # float, relative to t_start_s
    "t_exit_s",  # float | None (None when still inside at the trial end)
    "dwell_s",  # float | None
    "is_target",  # bool
    "is_perseverative",  # bool (decoy hole visited before in this trial)
    "before_encounter",  # bool (started before the first target visit)
)

#: Columns of the ``barnes_visits`` sheet: the experiment id, then VISIT_FIELDS.
EXCEL_VISIT_COLUMNS: Final[tuple[str, ...]] = ("experiment_id", *VISIT_FIELDS)

#: Scalar tidy columns and the ``protocol_metrics`` key each one reads, in order.
_SCALAR_TIDY_COLUMNS: tuple[tuple[str, str], ...] = (
    ("barnes_status", "status"),
    ("barnes_trial_type", "trial_type"),
    ("barnes_encounter_latency_s", "encounter_latency_s"),
    ("barnes_encounter_censored", "encounter_censored"),
    ("barnes_entry_latency_s", "entry_latency_s"),
    ("barnes_entry_censored", "entry_censored"),
    ("barnes_entry_source", "entry_source"),
    ("barnes_primary_errors", "primary_errors"),
    ("barnes_total_errors", "total_errors"),
    ("barnes_perseverative_errors", "perseverative_errors"),
    ("barnes_primary_path_cm", "primary_path_length_cm"),
    ("barnes_entry_path_cm", "entry_path_length_cm"),
    ("barnes_target_quadrant_time_s", "target_quadrant_time_s"),
    ("barnes_target_quadrant_pct", "target_quadrant_time_pct"),
    ("barnes_strategy", "strategy"),
    ("barnes_strategy_source", "strategy_source"),
    ("barnes_strategy_auto", "strategy_auto"),
    ("barnes_center_crossings", "strategy_features.center_crossings"),
    ("barnes_adjacent_fraction", "strategy_features.adjacent_transition_fraction"),
    ("barnes_probe_first_hole_offset", "probe_first_hole_offset"),
    ("barnes_probe_first_hole_score", "probe_first_hole_score"),
    ("barnes_probe_first_error_latency_s", "probe_first_error_latency_s"),
    ("barnes_probe_attempts_to_target", "probe_attempts_to_target"),
)


def barnes_tidy_columns(n_holes: int) -> tuple[str, ...]:
    """Ordered tidy columns of a Barnes project (appended after ``window_*``).

    The scalar columns, then one ``barnes_visits_dNN`` column per hole distance
    (``d00`` = target … ``d10`` = opposite for 20 holes). Constant within a
    project (``n_holes`` is a project parameter), so the unified report never sees
    a schema mismatch between two Barnes videos.
    """
    distances = range(max_offset(n_holes) + 1)
    return (
        *(column for column, _source in _SCALAR_TIDY_COLUMNS),
        *(f"barnes_visits_d{d:02d}" for d in distances),
    )


def tidy_column_source(column: str) -> str:
    """The ``protocol_metrics`` path a tidy column reads.

    Dotted paths go into nested dicts (``strategy_features.center_crossings``);
    ``barnes_visits_dNN`` reads ``visits_by_distance.<NN as int>``.

    Raises:
        KeyError: ``column`` is not a Barnes tidy column.
    """
    for name, source in _SCALAR_TIDY_COLUMNS:
        if name == column:
            return source
    match = re.fullmatch(r"barnes_visits_d(\d{2})", column)
    if match is not None:
        return f"visits_by_distance.{int(match.group(1))}"
    raise KeyError(column)
