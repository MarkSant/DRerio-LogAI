"""The ``7_AnalysisWindow_<base>.json`` artifact (ADR-011).

Written next to the trajectory, it records which window was applied to a
recording and why: the spec and its hash, the clock the instants are measured
on, the external events the engine saw, and the window found online (live, it
drove display and session end) and offline (it governs the analysis).

Writes are atomic (temporary file in the same folder + ``os.replace``), so a
crash leaves either the previous artifact or the new one, never a torn file.
Reads never raise: a missing, unreadable or invalid file is ``None``, which the
caller treats as "recompute".
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

import structlog
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

from zebtrack.core.conditions.evaluator import (
    ExternalEvent,
    WindowEvent,
    WindowReason,
    WindowResult,
)
from zebtrack.core.conditions.model import WindowSpec, spec_hash

__all__ = [
    "ARTIFACT_PREFIX",
    "ARTIFACT_SCHEMA",
    "AnalysisWindowArtifact",
    "ArtifactEvent",
    "ArtifactExternalEvent",
    "OfflineWindow",
    "OnlineWindow",
    "artifact_path",
    "read_artifact",
    "write_artifact",
]

logger = structlog.get_logger()

#: File-name prefix. Numbered after the 6_FrameLedger, and never a prefix of
#: ``3_CoordMovimento`` (globs over trajectories must not pick it up).
ARTIFACT_PREFIX = "7_AnalysisWindow_"
ARTIFACT_SCHEMA = "zebtrack.analysis_window/1"

_CONFIG = ConfigDict(
    frozen=True,
    extra="forbid",
    allow_inf_nan=False,
    validate_by_alias=True,
    validate_by_name=True,
    serialize_by_alias=True,
)


class ArtifactEvent(BaseModel):
    """A START or STOP instant as stored in the artifact."""

    model_config = _CONFIG

    frame: int = Field(ge=0)
    t_s: float
    reason: WindowReason | None = None

    @classmethod
    def from_window_event(cls, event: WindowEvent) -> ArtifactEvent:
        """Store the instant (back-dated) of an engine event."""
        return cls(frame=event.frame, t_s=event.t_s, reason=event.reason)


class ArtifactExternalEvent(BaseModel):
    """An external event as recorded for the session."""

    model_config = _CONFIG

    t_s: float
    source: Literal["arduino", "manual"]
    code: int | None = None

    @classmethod
    def from_event(cls, event: ExternalEvent) -> ArtifactExternalEvent:
        """Convert the engine's event type."""
        return cls(t_s=event.t_s, source=event.source, code=event.code)


def _event_or_none(event: WindowEvent | None) -> ArtifactEvent | None:
    return None if event is None else ArtifactEvent.from_window_event(event)


class OnlineWindow(BaseModel):
    """Window found live; drives display and session end only."""

    model_config = _CONFIG

    start: ArtifactEvent | None = None
    stop: ArtifactEvent | None = None

    @classmethod
    def from_result(cls, result: WindowResult) -> OnlineWindow:
        """Snapshot of the live evaluator's result (pending is fine here)."""
        return cls(start=_event_or_none(result.start), stop=_event_or_none(result.stop))


class OfflineWindow(BaseModel):
    """Window recomputed from the recorded inputs; governs the analysis.

    ``inputs`` holds the hashes of what the window was computed from
    (``trajectory_sha``, ``objects_sha``, ...) so a reuse can be validated.
    """

    model_config = _CONFIG

    start: ArtifactEvent | None = None
    stop: ArtifactEvent | None = None
    status: Literal["complete", "start_not_met", "censored", "inputs_missing"]
    inputs: dict[str, str | None] = Field(default_factory=dict)

    @classmethod
    def from_result(
        cls, result: WindowResult, *, inputs: Mapping[str, str | None]
    ) -> OfflineWindow:
        """Store a finished evaluation.

        Raises:
            ValueError: If the evaluation was not finished (``status="pending"``).
        """
        if result.status == "pending":
            raise ValueError("A pending window result cannot be stored as the offline window.")
        return cls(
            start=_event_or_none(result.start),
            stop=_event_or_none(result.stop),
            status=result.status,
            inputs=dict(inputs),
        )


class AnalysisWindowArtifact(BaseModel):
    """Content of ``7_AnalysisWindow_<base>.json``.

    ``spec_hash`` must be the hash of ``spec``; a file whose spec was edited by
    hand without updating the hash is rejected (and therefore recomputed).
    """

    model_config = _CONFIG

    schema_id: Literal["zebtrack.analysis_window/1"] = Field(
        default="zebtrack.analysis_window/1", alias="schema"
    )
    spec: WindowSpec
    spec_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    clock: Literal["pts", "capture_perf"]
    fps_video: float | None = Field(default=None, gt=0.0)
    aquarium_id: int | None = Field(default=None, ge=0)
    external_events: tuple[ArtifactExternalEvent, ...] = ()
    online: OnlineWindow = Field(default_factory=OnlineWindow)
    offline: OfflineWindow | None = None

    @classmethod
    def for_spec(cls, spec: WindowSpec, **fields: Any) -> AnalysisWindowArtifact:
        """Build an artifact for ``spec``, filling ``spec_hash`` from it."""
        return cls.model_validate({**fields, "spec": spec, "spec_hash": spec_hash(spec)})

    @model_validator(mode="after")
    def _hash_matches_spec(self) -> AnalysisWindowArtifact:
        expected = spec_hash(self.spec)
        if self.spec_hash != expected:
            raise PydanticCustomError(
                "spec_hash_mismatch",
                "spec_hash {stored} does not match the stored spec ({expected}).",
                {"stored": self.spec_hash, "expected": expected},
            )
        return self


def artifact_path(
    results_dir: str | os.PathLike[str], base: str, aquarium_id: int | None = None
) -> Path:
    """Where the artifact of ``base`` lives, next to its trajectory.

    Multi-aquarium mirrors the recorder: ``aquarium_{id+1}/`` holding
    ``7_AnalysisWindow_<base>_aquarium_{id+1}.json``.
    """
    folder = Path(results_dir)
    if aquarium_id is None:
        return folder / f"{ARTIFACT_PREFIX}{base}.json"
    suffix = f"aquarium_{aquarium_id + 1}"
    return folder / suffix / f"{ARTIFACT_PREFIX}{base}_{suffix}.json"


def write_artifact(
    path: str | os.PathLike[str], payload: AnalysisWindowArtifact | Mapping[str, Any]
) -> None:
    """Validate ``payload`` and write it atomically to ``path``.

    Raises:
        pydantic.ValidationError: If a mapping payload is not a valid artifact
            (nothing is written).
        OSError: If the write fails; the previous file, if any, is untouched and
            no temporary file is left behind.
    """
    target = Path(path)
    artifact = (
        payload
        if isinstance(payload, AnalysisWindowArtifact)
        else AnalysisWindowArtifact.model_validate(payload)
    )
    data = artifact.model_dump_json(indent=2)
    fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, target)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
    logger.info("conditions.artifact.write.success", path=str(target))


def read_artifact(path: str | os.PathLike[str]) -> AnalysisWindowArtifact | None:
    """Load the artifact at ``path``; ``None`` (with a warning) if absent or invalid."""
    target = Path(path)
    try:
        raw = target.read_bytes()
    except FileNotFoundError:
        logger.warning("conditions.artifact.read.missing", path=str(target))
        return None
    except OSError as exc:
        logger.warning("conditions.artifact.read.unreadable", path=str(target), error=str(exc))
        return None
    try:
        return AnalysisWindowArtifact.model_validate_json(raw)
    except ValueError as exc:
        logger.warning("conditions.artifact.read.invalid", path=str(target), error=str(exc))
        return None
