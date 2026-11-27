"""Ready-made analysis windows (ADR-011) — pure builders over :mod:`.model`.

A preset is a function that returns a :class:`~zebtrack.core.conditions.model.WindowSpec`.
The UI offers them as one-click starting points; the result is an ordinary spec that
the researcher can still edit, so nothing here is special-cased downstream.

Like the rest of the package this module is pure: no Tk, no settings, no detector.
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from zebtrack.core.conditions.model import (
    AllOfLevel,
    BurrowEntry,
    ClassPresence,
    ClassTarget,
    Delay,
    EndOfStream,
    External,
    FirstOf,
    Hold,
    Persist,
    RoiEdge,
    TriggerNode,
    WindowSpec,
)

__all__ = [
    "BARNES_BURROW_ROI",
    "BARNES_EXPERIMENTER_CLASS",
    "BARNES_START_BOX_CLASS",
    "BARNES_SUBJECT_CLASS",
    "LEGACY_TRIGGER_START_CODE",
    "LEGACY_TRIGGER_STOP_CODE",
    "barnes_maze_preset",
    "barnes_maze_preset_v1_arguments",
    "barnes_maze_preset_v2",
    "external_trigger_preset",
]

#: Class names of the lab's Barnes-maze weight. They are what the weight declares,
#: not display text, so they are never translated.
BARNES_START_BOX_CLASS = "start_box"
BARNES_EXPERIMENTER_CLASS = "experimenter"
BARNES_SUBJECT_CLASS = "rat"

#: Default name of the escape-hole ROI. It is the name the lab draws, matched
#: EXACTLY by the evaluator (``RoiEdge``), so it is a project-data token, never
#: translated. The editor adopts the project's own spelling when it differs.
BARNES_BURROW_ROI = "toca"

#: Codes of the pre-v8 "External Trigger Mode": the Arduino sends 1 to start
#: the recording and 0 to end it (see ``LiveConfigStep``'s tooltip).
LEGACY_TRIGGER_START_CODE = 1
LEGACY_TRIGGER_STOP_CODE = 0


def barnes_maze_preset(
    k_frames: int = 5,
    absent_s: float = 3.0,
    max_s: float = 240.0,
    burrow_roi: str | None = BARNES_BURROW_ROI,
) -> WindowSpec:
    """Barnes-maze window: start on release, stop on escape or at the ceiling.

    - **START** — the start box and the experimenter are both gone and the rat is
      visible, all together for ``k_frames`` consecutive processed frames. The
      event is back-dated to the first frame of that run.
    - **STOP** — the first of: the recording ends; the rat is absent for
      ``absent_s`` seconds (it entered the escape box, back-dated to the first
      absent frame); the rat enters the ``burrow_roi`` ROI (#650); ``max_s``
      seconds after START (protocol ceiling, censored).

    The burrow line exists because the rat is often still detected when the
    recording stops — the lab's videos end on the protocol's abort — so the
    absence line never fires and the trial came out censored at the end of the
    video. ``burrow_roi=None`` leaves it out. A project without a ROI of that
    name never fires it (the other lines still close the window); the analysis
    window editor warns about it instead of accepting it silently. It sits before
    the ceiling so that, on the rare frame where both fire, the trial reads as an
    escape rather than as censored.

    Production defaults (``5`` frames, ``3.0`` s, ``240.0`` s):

    - Both holds are back-dated, so a longer hold does not move the instant a
      window starts or stops — it only rejects shorter spurious runs. The cost of
      being conservative is therefore close to zero, and the defaults are a little
      longer than the acceptance fixture's.
    - ``k_frames=5`` is ~0.5 s on the lab's ~9.9 fps Barnes recordings: enough to
      ride over a one- or two-frame dropout of the experimenter's hand as it leaves
      the field of view.
    - ``absent_s=3.0`` tolerates a short missed detection of the rat on the open
      table without ending the trial early; a rat that steps back out of the box
      within that time resets the run, as the protocol wants (four paws in).
    - ``max_s=240.0`` is the protocol's trial ceiling (AUDIT §6).

    ``tests/fixtures/conditions/barnes_window.json`` predates the burrow line: it
    is this function with test numbers (``k_frames=3``, ``absent_s=2.0``) and
    ``burrow_roi=None``; its test calls it with those values explicitly.

    Raises:
        ValueError: ``max_s`` is not positive (a zero ceiling would close every
            window on its first frame), or ``burrow_roi`` is blank.
            ``pydantic.ValidationError`` for ``k_frames < 1`` or ``absent_s <= 0``.
    """
    if not max_s > 0:
        raise ValueError(f"max_s must be positive, got {max_s!r}")
    if burrow_roi is not None and not burrow_roi.strip():
        raise ValueError(f"burrow_roi must be a ROI name or None, got {burrow_roi!r}")
    start = _barnes_release(k_frames)
    stop_lines: list[TriggerNode] = [
        EndOfStream(),
        Persist(
            level=ClassPresence(
                target=ClassTarget.of_class(BARNES_SUBJECT_CLASS),
                present=False,
            ),
            hold=Hold(seconds=absent_s),
        ),
    ]
    if burrow_roi is not None:
        stop_lines.append(RoiEdge(roi=burrow_roi, edge="enter"))
    stop_lines.append(Delay(after="start", seconds=max_s))
    return WindowSpec(start=start, stop=FirstOf(children=tuple(stop_lines)))


def _barnes_release(k_frames: int) -> Persist:
    """START of every Barnes preset: box and experimenter gone, rat visible, held."""
    return Persist(
        level=AllOfLevel(
            children=(
                ClassPresence(
                    target=ClassTarget.of_class(BARNES_START_BOX_CLASS),
                    present=False,
                ),
                ClassPresence(
                    target=ClassTarget.of_class(BARNES_EXPERIMENTER_CLASS),
                    present=False,
                ),
                ClassPresence(
                    target=ClassTarget.of_class(BARNES_SUBJECT_CLASS),
                    present=True,
                ),
            )
        ),
        hold=Hold(frames=k_frames),
    )


def barnes_maze_preset_v2(
    *,
    k_frames: int = 5,
    max_s: float = 240.0,
    burrow_roi: str = BARNES_BURROW_ROI,
    entry_min_cover: float = 0.5,
    entry_max_visible_fraction: float = 0.35,
    entry_hold_s: float = 0.5,
    entry_absent_s: float = 3.0,
    entry_min_reference_frames: int = 10,
) -> WindowSpec:
    """Barnes-maze window v2 (#633): stop on the ENTRY into the escape hole.

    - **START** — identical to :func:`barnes_maze_preset` (v1).
    - **STOP** — the first of, in this order: the recording ends; the rat ENTERS
      ``burrow_roi`` (:class:`~zebtrack.core.conditions.model.BurrowEntry`, reason
      ``burrow_entry``); ``max_s`` seconds after START (protocol ceiling,
      censored).

    v1 stops on ``RoiEdge(burrow_roi, "enter")``, which under the default
    ``bbox_intersects`` rule fires on the first TOUCH of the hole — a nose poke —
    so the interval between the encounter and the entry fell outside the window.
    v2 waits for the entry, recognised from the box geometry because the rat
    weight is detection-only:

    - **(a)** at least ``entry_min_cover`` of the visible box is over the hole and
      its area is at most ``entry_max_visible_fraction`` of the rat's running
      median size since START (once ``entry_min_reference_frames`` detected frames
      make that median), held ``entry_hold_s`` seconds;
    - **(b)** the rat vanished for ``entry_absent_s`` seconds with its last box
      over the hole.

    Both are back-dated to the first frame of their run. A rat that never enters
    is censored at the ceiling. The keyword names mirror ``BarnesParams``
    (``analysis/protocols/barnes/contract.py``), which imports this module, so it
    cannot be passed here directly.

    Raises:
        ValueError: ``max_s`` is not positive, or ``burrow_roi`` is blank.
            ``pydantic.ValidationError`` for an out-of-range entry parameter.
    """
    if not max_s > 0:
        raise ValueError(f"max_s must be positive, got {max_s!r}")
    if not burrow_roi.strip():
        raise ValueError(f"burrow_roi must be a ROI name, got {burrow_roi!r}")
    entry = BurrowEntry(
        roi=burrow_roi,
        min_cover=entry_min_cover,
        max_visible_fraction=entry_max_visible_fraction,
        hold=Hold(seconds=entry_hold_s),
        absent_s=entry_absent_s,
        min_reference_frames=entry_min_reference_frames,
    )
    return WindowSpec(
        start=_barnes_release(k_frames),
        stop=FirstOf(children=(EndOfStream(), entry, Delay(after="start", seconds=max_s))),
    )


def barnes_maze_preset_v1_arguments(spec: WindowSpec | None) -> dict[str, Any] | None:
    """The arguments that make :func:`barnes_maze_preset` (v1) return ``spec`` exactly.

    ``None`` when ``spec`` is not a v1 Barnes preset (or was edited after it was
    applied). The editor uses it to OFFER the update to v2 — keeping the
    researcher's ``k_frames``, ``max_s`` and burrow ROI — never to apply it.
    """
    if spec is None or not isinstance(spec.start, Persist) or not isinstance(spec.stop, FirstOf):
        return None
    children = spec.stop.children
    if len(children) not in (3, 4):
        return None
    absence, ceiling = children[1], children[-1]
    burrow = children[2] if len(children) == 4 else None
    if not isinstance(absence, Persist) or absence.hold.seconds is None:
        return None
    if not isinstance(ceiling, Delay) or (burrow is not None and not isinstance(burrow, RoiEdge)):
        return None
    arguments: dict[str, Any] = {
        "k_frames": spec.start.hold.frames,
        "absent_s": absence.hold.seconds,
        "max_s": ceiling.seconds,
        "burrow_roi": None if burrow is None else burrow.roi,
    }
    if arguments["k_frames"] is None:
        return None
    try:
        rebuilt = barnes_maze_preset(**arguments)
    except (ValueError, ValidationError):
        return None
    return arguments if rebuilt == spec else None


def external_trigger_preset(
    start_code: int = LEGACY_TRIGGER_START_CODE,
    stop_code: int = LEGACY_TRIGGER_STOP_CODE,
) -> WindowSpec:
    """The pre-v8 "External Trigger Mode" expressed as a window (ADR-012).

    The Arduino's ``start_code`` opens the window and ``stop_code`` closes it.
    ``on_stop="end_session"`` keeps the legacy meaning of the stop code — "code 0
    ends the recording" — instead of merely marking the stop inside a session that
    keeps running.
    """
    return WindowSpec(
        start=External(source="arduino", code=start_code),
        stop=External(source="arduino", code=stop_code),
        on_stop="end_session",
    )
