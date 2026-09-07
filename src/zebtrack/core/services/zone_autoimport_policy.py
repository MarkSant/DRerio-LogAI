"""Single source for "may the app load this video's zone parquets on its own?".

Opening a video whose arena/ROIs are not yet in ``project_data`` used to run one
unconditional rule: *if a ``1_ProcessingArea_*`` / ``2_AreasOfInterest_*`` pair
can be found for it, load it and say nothing*. That rule was written for ONE
situation — a live recording, whose recorder writes those parquets into the
session folder while the in-memory zones stay under the reference-frame key. For
that case it is right and must keep working.

It is wrong for a pre-recorded project built on a folder that already carries
sidecars from an earlier study. ``VideoManager.scan_input_paths`` finds those
files next to the ``.mp4`` and records their paths on the video entry **even when
the wizard's import was declined**, and ``_resolve_source_zone_parquets`` searches
the video's own directory anyway, so declining the import in the wizard did not
stop them from being loaded on the first double-click. The arena and the ROIs of
a previous experiment silently became the arena and the ROIs of the new one.

The distinction this module draws is *provenance*, not file shape:

- Parquets **inside the project** were produced by this project (live session
  folder, or a previous run of the same video). Nobody was ever asked whether to
  use them; they are simply this project's own state. → ``AUTO``.
- Parquets **outside the project** are foreign data that the operator was already
  asked about in the wizard. An explicit "no" there is a decision, and honouring
  it is the whole point. → ``SKIP``.
- Anything else — foreign files with no recorded decision, e.g. a project created
  before the wizard stored one — is a judgement call that belongs to the
  operator, not to a silent default. → ``ASK``.

The scientific stake is why ``ASK`` exists at all instead of a second silent
default: an arena carried over from another recording still produces a complete,
plausible-looking report. Every distance, every ROI occupancy and every latency in
it is measured against the wrong geometry, and nothing in the output says so.
"""

from __future__ import annotations

import os
from enum import Enum
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger()

__all__ = [
    "ZoneAutoImport",
    "decide_zone_autoimport",
    "wizard_import_declined",
]


class ZoneAutoImport(Enum):
    """What to do with zone parquets found for a video that has no zones yet."""

    AUTO = "auto"
    """Load them without asking — they belong to this project."""

    ASK = "ask"
    """Foreign files, no recorded decision: let the operator choose."""

    SKIP = "skip"
    """Nothing to load, or the operator already declined these files."""


def _normalize(path: Any) -> str:
    """Case- and separator-insensitive form of *path* for comparison.

    Zone parquet paths reach this module from three writers that disagree on
    formatting: the wizard stores POSIX-style forward slashes, the video entries
    store Windows backslashes, and ``resolve_results_directory`` returns whatever
    ``pathlib`` produced. Comparing the raw strings misses matches that are the
    same file, which would send a declined import down the ``ASK`` branch.
    """
    if not path:
        return ""
    try:
        return os.path.normcase(os.path.normpath(str(path)))
    # except Exception justified: path values come from user projects and may be
    # malformed; an unusable path simply never matches.
    except Exception:  # pragma: no cover - defensive
        return ""


def _is_inside(candidate: Any, root: Any) -> bool:
    """Whether *candidate* lives under *root*.

    Uses string prefixes on normalized paths rather than ``Path.is_relative_to``
    on resolved paths: ``resolve()`` touches the filesystem and, on a OneDrive
    path that is not currently hydrated, can raise or hang. Provenance must be
    decidable without I/O.
    """
    candidate_norm = _normalize(candidate)
    root_norm = _normalize(root)
    if not candidate_norm or not root_norm:
        return False
    return candidate_norm == root_norm or candidate_norm.startswith(
        root_norm + os.sep if not root_norm.endswith(os.sep) else root_norm
    )


def _wizard_import_entries(project_data: Any) -> list[dict]:
    """The wizard's per-video import decisions, or an empty list."""
    if not isinstance(project_data, dict):
        return []

    metadata = project_data.get("_wizard_metadata")
    if not isinstance(metadata, dict):
        return []

    entries = metadata.get("import_config")
    if not isinstance(entries, list):
        return []

    return [entry for entry in entries if isinstance(entry, dict)]


def wizard_import_declined(project_data: Any, video_path: Any) -> bool | None:
    """Did the operator decline importing zones for *video_path* in the wizard?

    Returns ``True`` when a decision was recorded and it was "no", ``False`` when
    a decision was recorded and it asked for arena or ROIs, and ``None`` when the
    wizard left no record for this video — a project created before the wizard
    stored ``import_config``, or a video added afterwards.

    ``None`` and ``False`` currently steer :func:`decide_zone_autoimport` to the
    same ``ASK`` branch — a record that asked for an import, but whose zones are
    not in ``project_data``, describes an import that did not happen, and asking
    is as right there as it is for a project with no record at all. They stay
    distinct anyway: only ``True`` may suppress the question, so a caller can
    never reach "skip silently" from a *missing* answer, and the log can say
    which of the two it saw.
    """
    target = _normalize(video_path)
    if not target:
        return None

    for entry in _wizard_import_entries(project_data):
        if _normalize(entry.get("video")) != target:
            continue
        wants_arena = bool(entry.get("import_arena", False))
        wants_rois = bool(entry.get("import_rois", False))
        return not (wants_arena or wants_rois)

    return None


def decide_zone_autoimport(
    *,
    video_path: Any,
    candidates: dict[str, str] | None,
    project_path: Any,
    project_data: Any,
) -> ZoneAutoImport:
    """Decide how to treat zone parquets found on disk for *video_path*.

    Args:
        video_path: The video whose zones are missing from ``project_data``.
        candidates: Mapping of ``"arena"`` / ``"rois"`` to the parquet paths that
            were located for it. Empty or ``None`` means nothing was found.
        project_path: Root of the open project, or ``None`` when there is none
            (single-video and ad-hoc live workflows).
        project_data: The open project's data dictionary.

    Returns:
        The applicable :class:`ZoneAutoImport` member.
    """
    if not candidates:
        return ZoneAutoImport.SKIP

    # No project means no wizard, no per-video registry and no "inside the
    # project" to test against — the single-video and ad-hoc live workflows.
    # Their zones have always come from the files next to the media, and nothing
    # in this change is aimed at them.
    if not project_path:
        return ZoneAutoImport.AUTO

    outside = {key: path for key, path in candidates.items() if not _is_inside(path, project_path)}
    if not outside:
        log.debug(
            "zone_autoimport.auto.project_owned",
            video=os.path.basename(str(video_path)),
            files=sorted(candidates),
        )
        return ZoneAutoImport.AUTO

    declined = wizard_import_declined(project_data, video_path)
    if declined:
        log.info(
            "zone_autoimport.skip.wizard_declined",
            video=os.path.basename(str(video_path)),
            files=sorted(outside),
        )
        return ZoneAutoImport.SKIP

    log.info(
        "zone_autoimport.ask.foreign_parquets",
        video=os.path.basename(str(video_path)),
        files=sorted(outside),
        wizard_record=("absent" if declined is None else "import_requested"),
    )
    return ZoneAutoImport.ASK


def describe_candidate_origin(candidates: dict[str, str] | None) -> str:
    """Human-readable folder the *candidates* came from, for the ``ASK`` prompt.

    The operator cannot judge whether to accept foreign zones without seeing
    where they come from — "there are zones on disk" is exactly the information
    that made the silent import feel like a hidden setting.
    """
    if not candidates:
        return ""

    for key in ("arena", "rois"):
        path = candidates.get(key)
        if path:
            return str(Path(path).parent)

    first = next(iter(candidates.values()), "")
    return str(Path(first).parent) if first else ""
